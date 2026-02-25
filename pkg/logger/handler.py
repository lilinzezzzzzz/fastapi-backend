import sys
from datetime import UTC, time, timedelta, timezone as dt_timezone
from enum import StrEnum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import loguru

from pkg.toolkit import context
from pkg.toolkit.json import orjson_dumps
from pkg.toolkit.timer import format_iso_datetime

# 默认日志目录
_DEFAULT_BASE_LOG_DIR = Path("/tmp/fastapi_logs")

# 类型别名
RotationType = str | int | time | timedelta
RetentionType = str | int | timedelta
TimezoneType = str | ZoneInfo | dt_timezone


class LogFormat(StrEnum):
    """日志格式枚举"""

    JSON = "json"
    TEXT = "text"


class LoggerHandler:
    """
    日志管理器
    配置在实例化 (__init__) 时传入，并在 setup() 时生效。
    """

    DEFAULT_LOG_NAMESPACE: str = "default"

    def __init__(
        self,
        *,
        level: str = "INFO",
        base_log_dir: Path | None = None,
        use_subdir: bool = False,
        rotation: RotationType = time(0, 0, 0, tzinfo=UTC),
        retention: RetentionType = timedelta(days=30),
        compression: str | None = None,
        timezone: TimezoneType = "UTC",
        enqueue: bool = True,
        log_format: LogFormat = LogFormat.TEXT,
    ):
        """
        构造函数：接收所有配置参数并存储为实例属性。

        :param level: 日志等级 (e.g., "INFO", "DEBUG")
        :param base_log_dir: 日志存放的根目录，默认为当前文件父级路径下的 logs 目录
        :param use_subdir: 是否使用子目录分隔日志，True 则按 log_namespace 创建子目录，False 则所有日志存放在 base_log_dir 下
        :param rotation: 轮转策略 (默认: 每天 00:00, UTC时间)
        :param retention: 保留策略 (默认: 30天)
        :param compression: 压缩格式 (e.g., "zip")
        :param timezone: 日志时区，支持时区字符串（如 "UTC", "Asia/Shanghai"）、ZoneInfo 对象或 datetime.timezone（如 datetime.UTC），默认 "UTC"
        :param enqueue: 是否使用多进程安全的队列写入
        :param log_format: 日志格式 (LogFormat.JSON 或 LogFormat.TEXT，默认 LogFormat.TEXT)
        """

        self._logger = loguru.logger
        self._registered_namespaces: dict[str, dict[str, Any]] = {}
        self._is_initialized = False

        # --- 配置属性 ---
        self.level = level
        self.base_log_dir = base_log_dir or _DEFAULT_BASE_LOG_DIR
        self.use_subdir = use_subdir
        self.retention = retention
        self.compression = compression
        self.enqueue = enqueue
        self.log_format = log_format

        # --- 根据 log_format 确定格式化器 ---
        is_json = self.log_format == LogFormat.JSON
        self.console_format = self._json_formatter if is_json else self._console_formatter
        self.file_format = self._json_formatter if is_json else self._file_formatter
        self.colorize = not is_json

        # --- 时区处理 ---
        self.timezone = self._normalize_timezone(timezone)
        self._is_utc = self.timezone.key == "UTC"

        # --- 轮转策略处理 ---
        self.rotation = self._normalize_rotation(rotation)

    def _normalize_timezone(self, timezone: TimezoneType) -> ZoneInfo:
        """
        将不同类型的时区参数统一转换为 ZoneInfo 对象。

        Args:
            timezone: 时区参数，支持字符串、ZoneInfo 或 datetime.timezone

        Returns:
            ZoneInfo 对象

        Raises:
            ValueError: 不支持的时区类型（如非UTC的datetime.timezone）
            TypeError: 无效的参数类型
        """
        if isinstance(timezone, str):
            return ZoneInfo(timezone)
        elif isinstance(timezone, ZoneInfo):
            return timezone
        elif isinstance(timezone, dt_timezone):
            # datetime.timezone 类型（如 datetime.UTC）
            tz_name = str(timezone)
            if tz_name == "UTC":
                return ZoneInfo("UTC")
            else:
                raise ValueError(
                    f"Unsupported timezone: {timezone}. "
                    f"Use ZoneInfo for non-UTC timezones, e.g., ZoneInfo('Asia/Shanghai')."
                )
        else:
            raise TypeError(f"timezone must be str, ZoneInfo, or datetime.timezone, got {type(timezone).__name__}")

    def _normalize_rotation(self, rotation: RotationType) -> RotationType:
        """
        规范化轮转策略，处理 time 类型的时区问题。

        对于 time 类型的 rotation：
        - 无时区：自动使用 timezone 的时区
        - 有时区：必须与 timezone 一致

        Args:
            rotation: 轮转策略参数

        Returns:
            规范化后的轮转策略

        Raises:
            ValueError: rotation 时区与 timezone 不一致
        """
        if not isinstance(rotation, time):
            return rotation

        if rotation.tzinfo is None:
            # 无时区，自动使用 timezone 的时区
            return rotation.replace(tzinfo=self.timezone)

        # 有时区，检查是否与 timezone 一致
        rotation_tz_name = getattr(rotation.tzinfo, "key", None) or str(rotation.tzinfo)
        timezone_name = self.timezone.key or str(self.timezone)
        if rotation_tz_name != timezone_name:
            raise ValueError(
                f"rotation timezone ({rotation_tz_name}) must match timezone ({timezone_name}). "
                f"Use time({rotation.hour}, {rotation.minute}, {rotation.second}, tzinfo=self.timezone) "
                f"or omit tzinfo to auto-use timezone."
            )
        return rotation

    def _get_log_dir(self, log_namespace: str) -> Path:
        """
        获取指定命名空间的日志目录。

        Args:
            log_namespace: 日志命名空间

        Returns:
            日志目录路径
        """
        if self.use_subdir:
            return self.base_log_dir / log_namespace
        else:
            return self.base_log_dir

    def setup(self, *, write_to_file: bool = True, write_to_console: bool = True) -> "loguru.Logger":
        """
        应用配置并初始化系统日志。
        注意：setup 不再接收配置参数，而是使用 __init__ 中保存的属性。
        """
        self._logger.remove()
        self._registered_namespaces.clear()

        # 1. 准备基础配置
        config_params: dict[str, Any] = {
            "extra": {
                "trace_id": "-",
                "log_namespace": self.DEFAULT_LOG_NAMESPACE,
                "json_content": None,
            },
        }

        # 2. 根据时区配置挂载 patcher
        # 注意：patcher 影响日志文件名 {time:YYYY-MM-DD}.log 的时区
        # 保持文件名时间与日志内容时间一致
        config_params["patcher"] = self._make_timezone_patcher()

        self._logger.configure(**config_params)

        # 3. Console 输出
        if write_to_console:
            self._logger.add(
                sink=sys.stderr,
                level=self.level,
                enqueue=self.enqueue,
                colorize=self.colorize,
                diagnose=True,
                format=self.console_format,
                filter=self._filter_system,
            )

        # 4. File 输出 (System Log)
        if write_to_file:
            log_dir = self._get_log_dir(self.DEFAULT_LOG_NAMESPACE)
            self._ensure_dir(log_dir)
            sink_path = log_dir / "{time:YYYY-MM-DD}.log"

            self._logger.add(
                sink=sink_path,
                level=self.level,
                rotation=self.rotation,
                retention=self.retention,
                compression=self.compression,
                enqueue=self.enqueue,
                format=self.file_format,
                filter=self._filter_system,
            )

            self._registered_namespaces[self.DEFAULT_LOG_NAMESPACE] = {"sink_registered": True}

        tz_name = self.timezone.key if hasattr(self.timezone, "key") else str(self.timezone)
        self._logger.info(
            f"Logger initialized. Timezone: {tz_name} | Format: {self.log_format} | Rotation: {self.rotation} | Level: {self.level}"
        )
        self._is_initialized = True
        return self._logger

    def get_dynamic_logger(
        self,
        log_namespace: str,
        *,
        write_to_console: bool = False,
    ) -> "loguru.Logger":
        """
        获取动态命名空间的 Logger。
        使用实例属性 (self.rotation, self.retention, self.log_format 等) 创建新的 Sink。

        :param log_namespace: 日志命名空间标识
        :param write_to_console: 是否输出到控制台（仅针对该日志命名空间，不会重复输出）
        """
        if not self._is_initialized:
            raise RuntimeError("LoggerHandler is not initialized! Call setup() first.")

        if not log_namespace:
            raise ValueError(f"log_namespace cannot be empty, value = {log_namespace}")

        # 定义该命名空间专属的过滤器 (闭包)
        def _specific_filter(record):
            return record["extra"].get("log_namespace") == log_namespace

        # 获取或初始化配置
        if log_namespace not in self._registered_namespaces:
            self._registered_namespaces[log_namespace] = {
                "write_to_console": False,
                "sink_registered": False,
            }

        config = self._registered_namespaces[log_namespace]

        # 1. 检查并添加文件 Sink
        if not config["sink_registered"]:
            try:
                log_dir = self._get_log_dir(log_namespace)
                self._ensure_dir(log_dir)
                sink_path = log_dir / "{time:YYYY-MM-DD}.log"

                self._logger.add(
                    sink=sink_path,
                    level=self.level,
                    rotation=self.rotation,
                    retention=self.retention,
                    compression=self.compression,
                    enqueue=self.enqueue,
                    format=self.file_format,
                    serialize=False,
                    filter=_specific_filter,
                )

                config["sink_registered"] = True
                self._logger.info(f"System: Registered {self.log_format} sink for log_namespace '{log_namespace}'")

            except Exception as e:
                self._logger.error(f"System: Failed to register sink for '{log_namespace}'. Error: {e}")
                return self._logger.bind(log_namespace=self.DEFAULT_LOG_NAMESPACE, original_namespace=log_namespace)

        # 2. 检查并添加控制台 Sink
        if write_to_console and not config["write_to_console"]:
            self._logger.add(
                sink=sys.stderr,
                format=self.console_format,
                level=self.level,
                enqueue=self.enqueue,
                colorize=self.colorize,
                diagnose=True,
                filter=_specific_filter,
            )
            config["write_to_console"] = True
            self._logger.info(f"System: Added console sink for log_namespace '{log_namespace}'")

        # 返回绑定 log_namespace 的 logger
        return self._logger.bind(log_namespace=log_namespace)

    # --- 时间格式化 ---

    def _format_record_time(self, record: Any) -> str:
        """
        格式化日志记录的时间戳。

        注意：_make_timezone_patcher 已经将 record["time"] 转换为目标时区。
        此方法直接格式化时间，统一使用 ISO 8601 格式。

        Args:
            record: loguru 日志记录对象

        Returns:
            ISO 8601 格式的时间字符串
        """
        record_time = record["time"]

        # 处理 naive datetime（loguru 默认会带时区，但为了健壮性做处理）
        if record_time.tzinfo is None:
            # 为 naive datetime 添加时区信息
            record_time = record_time.replace(tzinfo=self.timezone)

        return format_iso_datetime(record_time)

    # --- 格式化器 ---

    def _console_formatter(self, record: Any) -> str:
        """控制台格式化器，仅输出纯文本，不包含 json_content"""
        # 获取 trace_id 和格式化时间
        trace_id = self._get_trace_id(record)
        formatted_time = self._format_record_time(record)

        fmt = (
            f"<green>{formatted_time}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            f"<magenta>{trace_id}</magenta> | "
            "<yellow>{extra[log_namespace]}</yellow> - <level>{message}</level>"
        )

        # 检查 json_content 是否存在且不为 None
        if record["extra"].get("json_content") is not None:
            # 换行并以青色显示 JSON 内容
            # loguru 会自动调用字典的 __str__ 或 __repr__
            fmt += "\n<cyan>{extra[json_content]}</cyan>"
        return fmt + "\n"

    def _file_formatter(self, record: Any) -> str:
        """
        File 文本动态格式化器 (log_format='text' 时使用)
        """
        trace_id = self._get_trace_id(record)
        formatted_time = self._format_record_time(record)

        fmt = (
            f"{formatted_time} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            f"{trace_id} | "
            "{extra[log_namespace]} - {message}"
        )

        # 检查并追加 json_content
        json_content = record["extra"].get("json_content")
        if json_content is not None:
            # 序列化为 JSON 字符串并存入 extra，避免直接输出 dict
            serialized = orjson_dumps(json_content, default=str)
            record["extra"]["_text_json"] = serialized
            # 这里选择换行追加，保持与 Console 视觉一致，且避免单行过长
            fmt += "\n{extra[_text_json]}"

        return fmt + "\n"

    def _json_formatter(self, record: Any) -> str:
        """JSON Lines 格式化器 (log_format='json' 时使用)"""
        trace_id = self._get_trace_id(record)
        formatted_time = self._format_record_time(record)

        extra_data = record["extra"].copy()
        json_content = extra_data.pop("json_content", None)
        extra_data.pop("_json_out", None)

        if not isinstance(json_content, (dict, list, str, type(None))):
            raise TypeError(f"json_content must be types or None. Got {type(json_content)}")

        log_record = {
            "time": formatted_time,
            "level": record["level"].name,
            "trace_id": trace_id,
            "location": f"{record['name']}.{record['function']}:{record['line']}",
            "text": "",
            "message": record["message"],
            **extra_data,
        }

        if json_content is not None:
            log_record["json_content"] = json_content

        serialized = orjson_dumps(log_record, default=str)
        record["extra"]["_json_out"] = serialized
        return "{extra[_json_out]}\n\n"

    # --- 辅助方法 ---
    def _make_timezone_patcher(self):
        """
        创建时区补丁函数。

        此补丁将 record["time"] 转换为配置的目标时区。
        影响：
        1. 日志文件名 {time:YYYY-MM-DD}.log 的时区
        2. 保持文件名时间与日志内容时间一致

        Returns:
            时区补丁函数
        """
        target_tz = self.timezone

        def patcher(record: Any):
            record["time"] = record["time"].astimezone(target_tz)

        return patcher

    @staticmethod
    def _filter_system(record: Any) -> bool:
        return record["extra"].get("log_namespace") == LoggerHandler.DEFAULT_LOG_NAMESPACE

    @staticmethod
    def _ensure_dir(path: Path):
        """确保目录存在，如果父目录不存在则自动创建"""
        path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _get_trace_id(cls, record: Any) -> str:
        """
        获取 trace_id，优先级：extra[trace_id] > context.get_trace_id() > "-"

        Args:
            record: 日志记录对象

        Returns:
            trace_id 字符串
        """
        trace_id = record["extra"].get("trace_id")

        # 如果 trace_id 无效，尝试从 context 获取
        if not context.is_valid_trace_id(trace_id):
            try:
                return context.get_trace_id()
            except LookupError:
                return "-"

        # 确保返回有效的 trace_id
        return trace_id
