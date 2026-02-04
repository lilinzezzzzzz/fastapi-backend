import sys
from datetime import UTC, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

import loguru

from pkg.toolkit import context
from pkg.toolkit.json import orjson_dumps
from pkg.toolkit.timer import format_iso_datetime

# 默认日志目录
_DEFAULT_BASE_LOG_DIR = Path("/tmp/fastapi_logs")

# 类型别名
RotationType = str | int | time | timedelta
RetentionType = str | int | timedelta


class LogFormat(StrEnum):
    """日志格式枚举"""

    JSON = "json"
    TEXT = "text"


class LoggerHandler:
    """
    日志管理器
    配置在实例化 (__init__) 时传入，并在 setup() 时生效。
    """

    SYSTEM_LOG_NAMESPACE: str = "system"

    def __init__(
        self,
        *,
        level: str = "INFO",
        base_log_dir: Path | None = None,
        system_subdir: str | None = None,
        rotation: RotationType = time(0, 0, 0, tzinfo=UTC),
        retention: RetentionType = timedelta(days=30),
        compression: str | None = None,
        use_utc: bool = True,
        enqueue: bool = True,
        log_format: LogFormat = LogFormat.TEXT,
    ):
        """
        构造函数：接收所有配置参数并存储为实例属性。

        :param level: 日志等级 (e.g., "INFO", "DEBUG")
        :param base_log_dir: 日志存放的根目录，默认为当前文件父级路径下的 logs 目录
        :param system_subdir: 系统日志子目录名，传 None 则直接存在 base_log_dir 下
        :param rotation: 轮转策略 (默认: 每天 00:00, UTC时间)
        :param retention: 保留策略 (默认: 30天)
        :param compression: 压缩格式 (e.g., "zip")
        :param use_utc: 是否强制使用 UTC 时间 (影响日志内容及轮转触发时间)
        :param enqueue: 是否使用多进程安全的队列写入
        :param log_format: 日志格式 (LogFormat.JSON 或 LogFormat.TEXT，默认 LogFormat.TEXT)
        """

        self._logger = loguru.logger
        self._registered_namespaces: dict[str, dict[str, Any]] = {}
        self._is_initialized = False

        # --- 配置属性 ---
        self.level = level
        self.base_log_dir = base_log_dir or _DEFAULT_BASE_LOG_DIR
        self.system_log_dir = (self.base_log_dir / system_subdir) if system_subdir else self.base_log_dir
        self.retention = retention
        self.compression = compression
        self.use_utc = use_utc
        self.enqueue = enqueue
        self.log_format = log_format

        # --- 根据 log_format 确定格式化器 ---
        is_json = self.log_format == LogFormat.JSON
        self.console_format = self._json_formatter if is_json else self._console_formatter
        self.file_format = self._json_formatter if is_json else self._file_formatter
        self.colorize = not is_json

        # --- 轮转策略的特殊处理 ---
        # 如果强制使用 UTC，且传入的 rotation 是默认的无时区 time 对象，
        # 则自动为其添加 UTC 时区，确保轮转时刻与日志时间一致。
        if self.use_utc and isinstance(rotation, time) and rotation.tzinfo is None:
            self.rotation = rotation.replace(tzinfo=UTC)
        else:
            self.rotation = rotation

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
                "log_namespace": self.SYSTEM_LOG_NAMESPACE,
                "json_content": None,
            },
        }

        # 2. 根据实例属性决定是否挂载 UTC 补丁
        if self.use_utc:
            config_params["patcher"] = self._utc_time_patcher

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
            self._ensure_dir(self.system_log_dir)
            sink_path = self.system_log_dir / "{time:YYYY-MM-DD}.log"

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

            self._registered_namespaces[self.SYSTEM_LOG_NAMESPACE] = {"sink_registered": True}

        mode_str = "UTC" if self.use_utc else "Local Time"
        self._logger.info(
            f"Logger initialized. Mode: {mode_str} | Format: {self.log_format} | Rotation: {self.rotation} | Level: {self.level}"
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
                self._ensure_dir(log_dir := self.base_log_dir / log_namespace)
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
                return self._logger.bind(log_namespace=self.SYSTEM_LOG_NAMESPACE, original_namespace=log_namespace)

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

    # --- 格式化器 ---

    @classmethod
    def _console_formatter(cls, record: Any) -> str:
        """控制台格式化器，仅输出纯文本，不包含 json_content"""
        # 获取 trace_id
        trace_id = cls._get_trace_id(record)

        fmt = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSSZ}</green> | "
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

    @classmethod
    def _file_formatter(cls, record: Any) -> str:
        """
        File 文本动态格式化器 (log_format='text' 时使用)
        """
        trace_id = cls._get_trace_id(record)

        fmt = (
            "{time:YYYY-MM-DD HH:mm:ss.SSSZ} | "
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

    @classmethod
    def _json_formatter(cls, record: Any) -> str:
        """JSON Lines 格式化器 (log_format='json' 时使用)"""
        trace_id = cls._get_trace_id(record)

        extra_data = record["extra"].copy()
        json_content = extra_data.pop("json_content", None)
        extra_data.pop("_json_out", None)

        if not isinstance(json_content, (dict, list, str, type(None))):
            raise TypeError(f"json_content must be types or None. Got {type(json_content)}")

        log_record = {
            "time": format_iso_datetime(record["time"]),
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
    @staticmethod
    def _utc_time_patcher(record: Any):
        record["time"] = record["time"].astimezone(UTC)

    @staticmethod
    def _filter_system(record: Any) -> bool:
        return record["extra"].get("log_namespace") == LoggerHandler.SYSTEM_LOG_NAMESPACE

    @staticmethod
    def _ensure_dir(path: Path):
        if not path.parent.exists():
            raise FileNotFoundError(f"Parent directory does not exist: {path.parent}")
        path.mkdir(exist_ok=True)

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

        # 如果 trace_id 为 None 或 "-"，尝试从 context 获取
        if trace_id is None:
            trace_id = context.get_trace_id()

        # 如果仍然没有，返回 "-"
        return trace_id
