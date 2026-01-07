import sys
from datetime import UTC, time, timedelta
from pathlib import Path
from typing import Any

import loguru

from pkg.toolkit.json import orjson_dumps
from pkg.toolkit.string import uuid6_unique_str_id

# 默认日志目录：/tmp/fastapi_{唯一字符}_logs
_DEFAULT_BASE_LOG_DIR = Path(f"/tmp/fastapi_{uuid6_unique_str_id()}_logs")

# 类型别名
RotationType = str | int | time | timedelta
RetentionType = str | int | timedelta


class LoggerManager:
    """
    日志管理器
    配置在实例化 (__init__) 时传入，并在 setup() 时生效。
    """

    SYSTEM_LOG_TYPE: str = "system"

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
        """
        self._logger = loguru.logger
        self._registered_types: dict[str, dict[str, Any]] = {}
        self._is_initialized = False

        # --- 配置属性 ---
        self.level = level
        self.base_log_dir = base_log_dir or _DEFAULT_BASE_LOG_DIR
        self.system_log_dir = (self.base_log_dir / system_subdir) if system_subdir else self.base_log_dir
        self.retention = retention
        self.compression = compression
        self.use_utc = use_utc
        self.enqueue = enqueue

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
        self._registered_types.clear()

        # 1. 准备基础配置
        config_params: dict[str, Any] = {
            "extra": {
                "trace_id": "-",
                "type": self.SYSTEM_LOG_TYPE,
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
                colorize=True,
                diagnose=True,
                format=self._console_formatter,
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
                format=self._file_formatter,
                filter=self._filter_system,
            )

            self._registered_types[self.SYSTEM_LOG_TYPE] = {"save_json": False}

        mode_str = "UTC" if self.use_utc else "Local Time"
        self._logger.info(f"Logger initialized. Mode: {mode_str} | Rotation: {self.rotation} | Level: {self.level}")
        self._is_initialized = True
        return self._logger

    def get_dynamic_logger(
        self,
        log_type: str,
        *,
        write_to_console: bool = False,
        save_json: bool = True,
    ) -> "loguru.Logger":
        """
        获取动态类型的 Logger。
        使用实例属性 (self.rotation, self.retention 等) 创建新的 Sink。

        :param log_type: 日志类型标识
        :param write_to_console: 是否输出到控制台（仅针对该日志类型，不会重复输出）
        :param save_json: 文件是否使用 JSON 格式
        """
        if not self._is_initialized:
            raise RuntimeError("LoggerManager is not initialized! Call setup() first.")

        if not log_type:
            raise ValueError(f"log_type cannot be empty, value = {log_type}")

        # 为了避免 JSON 和 text sink 互相干扰，使用不同的内部 key
        # JSON 日志使用 "{log_type}_json"，text 日志使用原始 "{log_type}"
        internal_key = f"{log_type}_json" if save_json else log_type

        # 定义该设备专属的过滤器 (闭包)
        # 这保证了即使添加多个 stderr sink，每个 sink 也只处理自己 internal_key 的消息
        def _specific_filter(record):
            return record["extra"].get("log_type") == internal_key

        # 获取或初始化配置（使用 internal_key 作为注册的 key）
        if internal_key not in self._registered_types:
            self._registered_types[internal_key] = {
                "format": "json" if save_json else "text",
                "write_to_console": False,
                "sink_registered": False,
            }

        config = self._registered_types[internal_key]

        # 1. 检查并添加文件 Sink
        if not config["sink_registered"]:
            try:
                # 文件存储在原始 log_type 目录下（而不是 internal_key）
                self._ensure_dir(log_dir := self.base_log_dir / log_type)
                sink_path = log_dir / "{time:YYYY-MM-DD}.log"

                log_format = self._json_formatter if save_json else self._file_formatter

                self._logger.add(
                    sink=sink_path,
                    level=self.level,
                    rotation=self.rotation,
                    retention=self.retention,
                    compression=self.compression,
                    enqueue=self.enqueue,
                    format=log_format,
                    serialize=False,
                    filter=_specific_filter,
                )

                config["sink_registered"] = True
                self._logger.info(f"System: Registered {config['format']} sink for log_type '{log_type}'")

            except Exception as e:
                self._logger.error(f"System: Failed to register sink for '{log_type}'. Error: {e}")
                return self._logger.bind(log_type=self.SYSTEM_LOG_TYPE, original_type=log_type)

        # 2. 检查并添加控制台 Sink
        if write_to_console and not config["write_to_console"]:
            self._logger.add(
                sink=sys.stderr,
                format=self._console_formatter,
                level=self.level,
                enqueue=self.enqueue,
                colorize=True,
                diagnose=True,
                filter=_specific_filter,
            )
            config["write_to_console"] = True
            self._logger.info(f"System: Added console sink for log_type '{log_type}'")

        # 返回绑定 internal_key 的 logger，确保日志只被对应的 sink 处理
        return self._logger.bind(log_type=internal_key)

    # --- 格式化器 ---

    @staticmethod
    def _console_formatter(record: Any) -> str:
        fmt = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<magenta>{extra[trace_id]}</magenta> | "
            "<yellow>{extra[type]}</yellow> - <level>{message}</level>"
        )

        # 检查 json_content 是否存在且不为 None
        if record["extra"].get("json_content") is not None:
            # 换行并以青色显示 JSON 内容
            # loguru 会自动调用字典的 __str__ 或 __repr__
            fmt += "\n<cyan>{extra[json_content]}</cyan>"
        return fmt + "\n"

    @staticmethod
    def _file_formatter(record: Any) -> str:
        """
        File 文本动态格式化器 (save_json=False 时使用)
        """
        fmt = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{extra[trace_id]} | "
            "{extra[type]} - {message}"
        )

        # 检查并追加 json_content
        if record["extra"].get("json_content") is not None:
            # 这里选择换行追加，保持与 Console 视觉一致，且避免单行过长
            # 如果希望单行，可以将 \n 替换为 | 或 -
            fmt += "\n{extra[json_content]}"

        return fmt + "\n"

    @staticmethod
    def _json_formatter(record: Any) -> str:
        """JSON Lines 格式化器 (save_json=True 时使用)"""
        extra_data = record["extra"].copy()
        json_content = extra_data.pop("json_content", None)

        if not isinstance(json_content, (dict, list, str, type(None))):
            raise TypeError(f"json_content must be types or None. Got {type(json_content)}")

        log_record = {
            "time": record["time"].strftime("%Y-%m-%d %H:%M:%S.%f"),
            "level": record["level"].name,
            "name": record["name"],
            "function": record["function"],
            "line": record["line"],
            "text": "",
            "message": record["message"],
            **extra_data,
        }

        if json_content is not None:
            log_record["json_content"] = json_content

        serialized = orjson_dumps(log_record, default=str)
        record["extra"]["serialized_json"] = serialized
        return "{extra[serialized_json]}\n"

    # --- 辅助方法 ---
    @staticmethod
    def _utc_time_patcher(record: Any):
        record["time"] = record["time"].astimezone(UTC)

    @staticmethod
    def _filter_system(record: Any) -> bool:
        return record["extra"].get("type") == LoggerManager.SYSTEM_LOG_TYPE

    @staticmethod
    def _ensure_dir(path: Path):
        if not path.parent.exists():
            raise FileNotFoundError(f"Parent directory does not exist: {path.parent}")
        path.mkdir(exist_ok=True)


logger = LoggerManager().setup()
