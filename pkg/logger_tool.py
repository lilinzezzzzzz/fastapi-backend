import logging
import os
import sys
from pathlib import Path
from typing import Any, Set

import loguru

# 假设 pkg 导入路径
from pkg import BASE_DIR


class LogConfig:
    """日志配置中心"""
    LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    BASE_LOG_DIR: Path = BASE_DIR / "logs"
    DEFAULT_DIR: Path = BASE_LOG_DIR / "default"

    # 通用配置
    ROTATION: str = os.getenv("LOG_ROTATION", "00:00")
    RETENTION: str = os.getenv("LOG_RETENTION", "30 days")
    COMPRESSION: str = "zip"

    # 格式配置
    # Console 使用文本格式 (方便看)
    CONSOLE_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <magenta>{extra[trace_id]}</magenta> | <yellow>{extra[type]}</yellow> - <level>{message}</level>"
    # File 使用 JSON 序列化，FORMAT 参数在 serialize=True 时会被 loguru 忽略或作为 text 字段，此处保留供参考
    FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {extra[trace_id]} | {extra[type]} - {message}"


class LoggerManager:
    """日志管理器：负责 Loguru 的初始化、Sink 注册和动态日志获取"""

    def __init__(self):
        self._logger = loguru.logger
        self._registered_types: Set[str] = set()
        self._is_initialized = False

    def setup(self, write_to_file: bool = True, write_to_console: bool = True) -> "loguru.Logger":
        """
        初始化日志配置 (相当于之前的 _init_logger)
        """
        # 防止重复初始化
        self._logger.remove()
        self._registered_types.clear()

        # 1. 清除第三方库(uvicorn)的默认 handler
        # self._remove_uvicorn_handlers()

        # 2. 设置默认 Context (type='default')
        self._logger.configure(extra={"trace_id": "-", "type": "default"})

        # 3. 配置控制台输出 (Human Readable)
        if write_to_console:
            self._logger.add(
                sink=sys.stderr,
                format=LogConfig.CONSOLE_FORMAT,
                level=LogConfig.LEVEL,
                enqueue=True,
                colorize=True,
                diagnose=True
            )

        # 4. 配置文件输出 (JSON)
        if write_to_file:
            self._ensure_dir(LogConfig.DEFAULT_DIR)

            # --- Sink A: 静态默认日志 (type=default) ---
            self._logger.add(
                sink=LogConfig.DEFAULT_DIR / "app_{time:YYYY-MM-DD}.log",
                level=LogConfig.LEVEL,
                rotation=LogConfig.ROTATION,
                retention=LogConfig.RETENTION,
                compression=LogConfig.COMPRESSION,
                enqueue=True,
                format=LogConfig.FILE_FORMAT,
                filter=self._filter_default
            )

            self._registered_types.add("default")

        self._logger.info("Logger initialized successfully.")
        self._is_initialized = True
        return self._logger

    def get_dynamic_logger(
            self,
            log_type: str,
            *,
            write_to_file: bool = True,
            write_to_console: bool = False
    ) -> "loguru.Logger":
        """
        获取动态类型的 Logger (相当于之前的 get_logger_by_dynamic_type)
        如果该类型是第一次出现，会自动注册对应的文件 Sink
        """
        if not self._is_initialized:
            raise RuntimeError("LoggerManager is not initialized! You MUST call 'logger_manager.setup()' first.")

        # 1. 缓存命中，直接返回
        if log_type in self._registered_types:
            return self._logger.bind(type=log_type)

        # 2. 动态注册新 Sink
        try:
            log_dir = LogConfig.BASE_LOG_DIR / log_type
            self._ensure_dir(log_dir)

            sink_path = log_dir / "{time:YYYY-MM-DD}.log"

            # 使用闭包锁定当前的 log_type
            def _specific_filter(record):
                return record["extra"].get("type") == log_type

            if write_to_console:
                self._logger.add(
                    sink=sys.stderr,
                    format=LogConfig.CONSOLE_FORMAT,
                    level=LogConfig.LEVEL,
                    enqueue=True,
                    colorize=True,
                    diagnose=True,
                    filter=_specific_filter
                )

            if write_to_file:
                self._logger.add(
                    sink=sink_path,
                    level=LogConfig.LEVEL,
                    rotation=LogConfig.ROTATION,
                    retention=LogConfig.RETENTION,
                    compression=LogConfig.COMPRESSION,
                    enqueue=True,
                    format=self._empty_format,
                    serialize=True,
                    filter=_specific_filter
                )

            self._registered_types.add(log_type)

            # 记录系统日志
            self._logger.info(f"System: Registered new log sink for type '{log_type}'")

        except Exception as e:
            # 降级处理：注册失败时，回退到 default，并记录错误
            self._logger.error(f"System: Failed to register sink for '{log_type}'. Error: {e}")
            return self._logger.bind(type="default", original_type=log_type)

        return self._logger.bind(type=log_type)

    @staticmethod
    def _empty_format(_: Any) -> str:
        """
        返回空字符串。
        当 serialize=True 时，format 函数的返回值会被赋值给 JSON 日志中的 "text" 字段。
        """
        return ""

    @staticmethod
    def _filter_default(record: Any) -> bool:
        return record["extra"].get("type") == "default"

    @staticmethod
    def _remove_uvicorn_handlers():
        logging.getLogger("uvicorn.access").handlers = []
        logging.getLogger("uvicorn.error").handlers = []
        logging.getLogger("uvicorn").handlers = []

    @staticmethod
    def _ensure_dir(path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    @property
    def server_logger(self):
        """返回原始的 loguru logger 对象"""
        return self._logger


# 1. 实例化管理器
logger_manager = LoggerManager()
# 2. 执行初始化 (模块加载时执行)
logger = logger_manager.setup()
# 3. 导出常用的动态 logger 获取方法，保持 API 简洁
get_dynamic_logger = logger_manager.get_dynamic_logger
