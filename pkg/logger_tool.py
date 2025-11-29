import os
import sys
from pathlib import Path
from typing import Any

import loguru

# 确保这里的导入路径与你的项目结构一致
from pkg import BASE_DIR, orjson_dumps


class LoggerManager:
    """
    日志管理器
    集成了配置、初始化、动态Sink注册和自定义格式化功能。
    """

    # --- 1. 核心常量定义 ---
    SYSTEM_LOG_TYPE: str = "system"

    # --- 2. 配置部分 ---
    LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # 路径配置
    BASE_LOG_DIR: Path = BASE_DIR / "logs"
    # 直接在类定义中引用上面的 SYSTEM_LOG_TYPE
    SYSTEM_LOG_DIR: Path = BASE_LOG_DIR / SYSTEM_LOG_TYPE

    # 轮转与保留配置
    ROTATION: str = os.getenv("LOG_ROTATION", "00:00")
    RETENTION: str = os.getenv("LOG_RETENTION", "30 days")
    COMPRESSION: str = "zip"

    # 格式配置
    CONSOLE_FORMAT = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<magenta>{extra[trace_id]}</magenta> | "
        "<yellow>{extra[type]}</yellow> - <level>{message}</level>"
    )

    FILE_FORMAT = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{extra[trace_id]} | "
        "{extra[type]} - {message}"
    )

    def __init__(self):
        self._logger = loguru.logger
        # 存储已注册的类型及其配置: {"payment": {"save_json": True}}
        self._registered_types: dict[str, dict[str, Any]] = {}
        self._is_initialized = False

    def setup(self, write_to_file: bool = True, write_to_console: bool = True) -> "loguru.Logger":
        """初始化系统日志 (System Logger)"""
        self._logger.remove()
        self._registered_types.clear()

        # 1. 设置默认 Context (使用 self.SYSTEM_LOG_TYPE)
        self._logger.configure(extra={"trace_id": "-", "type": self.SYSTEM_LOG_TYPE, "json_content": None})

        # 2. Console 输出
        if write_to_console:
            self._logger.add(
                sink=sys.stderr,
                format=self.CONSOLE_FORMAT,
                level=self.LEVEL,
                enqueue=True,
                colorize=True,
                diagnose=True
            )

        # 3. File 输出 (System Log)
        if write_to_file:
            self._ensure_dir(self.SYSTEM_LOG_DIR)

            # 注册 System sink (默认为文本格式)
            self._logger.add(
                sink=self.SYSTEM_LOG_DIR / "{time:YYYY-MM-DD}.log",
                level=self.LEVEL,
                rotation=self.ROTATION,
                retention=self.RETENTION,
                compression=self.COMPRESSION,
                enqueue=True,
                format=self.FILE_FORMAT,
                filter=self._filter_system  # 使用内部静态方法作为过滤器
            )

            # 记录 System 类型配置
            self._registered_types[self.SYSTEM_LOG_TYPE] = {"save_json": False}

        self._logger.info("Logger initialized successfully.")
        self._is_initialized = True
        return self._logger

    def get_dynamic_logger(
            self,
            log_type: str,
            *,
            write_to_file: bool = True,
            write_to_console: bool = False,
            save_json: bool = True
    ) -> "loguru.Logger":
        """
        获取动态类型的 Logger
        :param log_type: 日志业务类型 (如 "payment", "user")
        :param save_json: 是否保存为 JSON 格式 (默认为 True)
        :param write_to_console:
        :param write_to_file:
        """
        if not self._is_initialized:
            raise RuntimeError("LoggerManager is not initialized! Call setup() first.")

        # --- 校验逻辑 ---
        if log_type in self._registered_types:
            existing_config = self._registered_types[log_type]
            existing_save_json = existing_config.get("save_json")

            if existing_save_json != save_json:
                raise ValueError(
                    f"Log type '{log_type}' is already registered with save_json={existing_save_json}, "
                    f"but requested with save_json={save_json}. Configuration conflict!"
                )
            return self._logger.bind(type=log_type)

        # --- 注册新 Sink ---
        try:
            log_dir = self.BASE_LOG_DIR / log_type
            self._ensure_dir(log_dir)
            sink_path = log_dir / "{time:YYYY-MM-DD}.log"

            # 闭包过滤器
            def _specific_filter(record):
                return record["extra"].get("type") == log_type

            if write_to_console:
                self._logger.add(
                    sink=sys.stderr,
                    format=self.CONSOLE_FORMAT,
                    level=self.LEVEL,
                    enqueue=True,
                    colorize=True,
                    filter=_specific_filter
                )

            if write_to_file:
                # 选择格式化器
                log_format = self._json_formatter if save_json else self.FILE_FORMAT

                self._logger.add(
                    sink=sink_path,
                    level=self.LEVEL,
                    rotation=self.ROTATION,
                    retention=self.RETENTION,
                    compression=self.COMPRESSION,
                    enqueue=True,
                    format=log_format,
                    serialize=False,
                    filter=_specific_filter
                )

            # 记录配置
            self._registered_types[log_type] = {"save_json": save_json}

            self._logger.info(f"System: Registered new log sink for type '{log_type}' (save_json={save_json})")

        except Exception as e:
            # 发生错误时回退到 System 日志
            self._logger.error(f"System: Failed to register sink for '{log_type}'. Error: {e}")
            return self._logger.bind(type=self.SYSTEM_LOG_TYPE, original_type=log_type)

        return self._logger.bind(type=log_type)

    @staticmethod
    def _json_formatter(record: Any) -> str:
        """
        自定义 JSON 格式化器
        """
        extra_data = record["extra"].copy()
        json_content = extra_data.pop("json_content", None)

        if not isinstance(json_content, (dict, list, str, type(None))):
            raise TypeError(f"json_content must be a dict, list, str, or None. Got {type(json_content)}")

        log_record = {
            "time": record["time"].strftime("%Y-%m-%d %H:%M:%S.%f"),
            "level": record["level"].name,
            "name": record["name"],
            "function": record["function"],
            "line": record["line"],
            "text": "",
            "message": record["message"],
            "extra": extra_data
        }

        if json_content is not None:
            log_record["json_content"] = json_content

        serialized = orjson_dumps(log_record, default=str)
        record["extra"]["serialized_json"] = serialized

        return "{extra[serialized_json]}\n"

    @staticmethod
    def _filter_system(record: Any) -> bool:
        """过滤系统默认日志"""
        # 静态方法中通过类名访问常量
        return record["extra"].get("type") == LoggerManager.SYSTEM_LOG_TYPE

    @staticmethod
    def _ensure_dir(path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


# 实例化
logger_manager = LoggerManager()
logger = logger_manager.setup()
get_dynamic_logger = logger_manager.get_dynamic_logger
