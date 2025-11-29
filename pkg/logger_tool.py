import os
import sys
from pathlib import Path
from typing import Any
from datetime import timezone

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
        self._registered_types: dict[str, dict[str, Any]] = {}
        self._is_initialized = False

    def setup(
            self,
            *,
            write_to_file: bool = True,
            write_to_console: bool = True,
            use_utc: bool = True
    ) -> "loguru.Logger":
        """
        初始化系统日志 (System Logger)
        :param use_utc: 是否强制使用 UTC 时间 (影响控制台、文件时间戳及文件名)
        :param write_to_console
        :param write_to_file
        """
        self._logger.remove()
        self._registered_types.clear()

        # 1. 准备基础配置
        config_params = {
            "extra": {"trace_id": "-", "type": self.SYSTEM_LOG_TYPE, "json_content": None}
        }

        # 2. 根据参数决定是否挂载 UTC 补丁
        if use_utc:
            config_params["patcher"] = self._utc_time_patcher

        self._logger.configure(**config_params)

        # 3. Console 输出
        if write_to_console:
            self._logger.add(
                sink=sys.stderr,
                format=self.CONSOLE_FORMAT,
                level=self.LEVEL,
                enqueue=True,
                colorize=True,
                diagnose=True
            )

        # 4. File 输出 (System Log)
        if write_to_file:
            self._ensure_dir(self.SYSTEM_LOG_DIR)

            self._logger.add(
                sink=self.SYSTEM_LOG_DIR / "{time:YYYY-MM-DD}.log",
                level=self.LEVEL,
                rotation=self.ROTATION,
                retention=self.RETENTION,
                compression=self.COMPRESSION,
                enqueue=True,
                format=self.FILE_FORMAT,
                filter=self._filter_system
            )

            # 记录 System 类型配置
            self._registered_types[self.SYSTEM_LOG_TYPE] = {"save_json": False}

        mode_str = "UTC" if use_utc else "Local Time"
        self._logger.info(f"Logger initialized successfully ({mode_str} Mode).")
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
        """获取动态类型的 Logger"""
        if not self._is_initialized:
            raise RuntimeError("LoggerManager is not initialized! Call setup() first.")

        if log_type in self._registered_types:
            existing_config = self._registered_types[log_type]
            existing_save_json = existing_config.get("save_json")
            if existing_save_json != save_json:
                raise ValueError(
                    f"Configuration conflict for '{log_type}'."
                )
            return self._logger.bind(type=log_type)

        try:
            log_dir = self.BASE_LOG_DIR / log_type
            self._ensure_dir(log_dir)
            sink_path = log_dir / "{time:YYYY-MM-DD}.log"

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

            self._registered_types[log_type] = {"save_json": save_json}
            self._logger.info(f"System: Registered new log sink for type '{log_type}'")

        except Exception as e:
            self._logger.error(f"System: Failed to register sink for '{log_type}'. Error: {e}")
            return self._logger.bind(type=self.SYSTEM_LOG_TYPE, original_type=log_type)

        return self._logger.bind(type=log_type)

    # --- UTC 转换补丁 ---
    @staticmethod
    def _utc_time_patcher(record: Any):
        """将记录时间强制转换为 UTC"""
        record["time"] = record["time"].astimezone(timezone.utc)

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
        return record["extra"].get("type") == LoggerManager.SYSTEM_LOG_TYPE

    @staticmethod
    def _ensure_dir(path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


# 实例化
logger_manager = LoggerManager()

# 显式指定使用 UTC
logger = logger_manager.setup(use_utc=True)

get_dynamic_logger = logger_manager.get_dynamic_logger
