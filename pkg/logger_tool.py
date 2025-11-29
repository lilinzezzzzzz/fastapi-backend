import os
import sys
from pathlib import Path
from typing import Any

import loguru

# 确保这里的导入路径与你的项目结构一致
from pkg import BASE_DIR, orjson_dumps


class LogConfig:
    """日志配置中心"""
    LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    BASE_LOG_DIR: Path = BASE_DIR / "logs"
    DEFAULT_DIR: Path = BASE_LOG_DIR / "default"

    # 通用配置
    ROTATION: str = os.getenv("LOG_ROTATION", "00:00")
    RETENTION: str = os.getenv("LOG_RETENTION", "30 days")
    COMPRESSION: str = "zip"

    # Console 格式
    CONSOLE_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <magenta>{extra[trace_id]}</magenta> | <yellow>{extra[type]}</yellow> - <level>{message}</level>"

    # File 格式 (文本模式使用)
    FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {extra[trace_id]} | {extra[type]} - {message}"


class LoggerManager:
    """日志管理器"""

    def __init__(self):
        self._logger = loguru.logger
        # 修改: Value 变为字典，用于存储详细配置信息
        # 结构示例: {"payment": {"save_json": True, "path": "..."}}
        self._registered_types: dict[str, dict[str, Any]] = {}
        self._is_initialized = False

    def setup(self, write_to_file: bool = True, write_to_console: bool = True) -> "loguru.Logger":
        self._logger.remove()
        self._registered_types.clear()

        # 1. 设置默认 Context
        self._logger.configure(extra={"trace_id": "-", "type": "default", "json_content": None})

        # 2. Console 输出
        if write_to_console:
            self._logger.add(
                sink=sys.stderr,
                format=LogConfig.CONSOLE_FORMAT,
                level=LogConfig.LEVEL,
                enqueue=True,
                colorize=True,
                diagnose=True
            )

        # 3. File 输出 (Default)
        if write_to_file:
            self._ensure_dir(LogConfig.DEFAULT_DIR)
            # 默认日志目前配置为普通文本格式 (save_json=False)
            self._logger.add(
                sink=LogConfig.DEFAULT_DIR / "{time:YYYY-MM-DD}.log",
                level=LogConfig.LEVEL,
                rotation=LogConfig.ROTATION,
                retention=LogConfig.RETENTION,
                compression=LogConfig.COMPRESSION,
                enqueue=True,
                format=LogConfig.FILE_FORMAT,
                filter=self._filter_default
            )
            # 修改: 注册默认类型，使用字典存储配置
            self._registered_types["default"] = {"save_json": False}

        self._logger.info("Logger initialized successfully.")
        self._is_initialized = True
        return self._logger

    def get_dynamic_logger(
            self,
            log_type: str,
            *,
            write_to_file: bool = True,
            write_to_console: bool = False,
            save_json: bool = True  # 修改: 参数名 is_json -> save_json
    ) -> "loguru.Logger":

        if not self._is_initialized:
            raise RuntimeError("LoggerManager is not initialized!")

        # --- 校验逻辑 ---
        if log_type in self._registered_types:
            # 获取已存在的配置
            existing_config = self._registered_types[log_type]
            existing_save_json = existing_config.get("save_json")

            # 对比配置是否冲突
            if existing_save_json != save_json:
                raise ValueError(
                    f"Log type '{log_type}' is already registered with save_json={existing_save_json}, "
                    f"but requested with save_json={save_json}. "
                    f"Configuration conflict!"
                )
            return self._logger.bind(type=log_type)

        try:
            log_dir = LogConfig.BASE_LOG_DIR / log_type
            self._ensure_dir(log_dir)
            sink_path = log_dir / "{time:YYYY-MM-DD}.log"

            def _specific_filter(record):
                return record["extra"].get("type") == log_type

            if write_to_console:
                self._logger.add(
                    sink=sys.stderr,
                    format=LogConfig.CONSOLE_FORMAT,
                    level=LogConfig.LEVEL,
                    enqueue=True,
                    colorize=True,
                    filter=_specific_filter
                )

            if write_to_file:
                # 根据参数选择格式化器
                if save_json:
                    log_format = self._json_formatter
                else:
                    log_format = LogConfig.FILE_FORMAT

                self._logger.add(
                    sink=sink_path,
                    level=LogConfig.LEVEL,
                    rotation=LogConfig.ROTATION,
                    retention=LogConfig.RETENTION,
                    compression=LogConfig.COMPRESSION,
                    enqueue=True,
                    format=log_format,
                    serialize=False,
                    filter=_specific_filter
                )

            # 修改: 注册新类型，存入字典配置
            self._registered_types[log_type] = {
                "save_json": save_json,
                # 你以后可以在这里扩展更多字段，例如:
                # "path": str(sink_path),
                # "retention": LogConfig.RETENTION
            }

            self._logger.info(f"System: Registered new log sink for type '{log_type}' (save_json={save_json})")

        except Exception as e:
            self._logger.error(f"System: Failed to register sink for '{log_type}'. Error: {e}")
            return self._logger.bind(type="default", original_type=log_type)

        return self._logger.bind(type=log_type)

    @staticmethod
    def _json_formatter(record: Any) -> str:
        """
        自定义 JSON 格式化器
        """
        extra_data = record["extra"].copy()
        json_content = extra_data.pop("json_content", None)

        if not isinstance(json_content, dict | list | str | None):
            raise TypeError("json_content must be a dict, list, str, or None")

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
    def _filter_default(record: Any) -> bool:
        return record["extra"].get("type") == "default"

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
