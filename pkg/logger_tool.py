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
    # 只有 Default 是静态定义的
    DEFAULT_DIR: Path = BASE_LOG_DIR / "default"

    FILE_NAME: str = "{time:YYYY-MM-DD}.log"
    ROTATION: str = os.getenv("LOG_ROTATION", "00:00")
    RETENTION: str = os.getenv("LOG_RETENTION", "30 days")
    COMPRESSION: str = "zip"

    CONSOLE_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <magenta>{extra[trace_id]}</magenta> | <yellow>{extra[type]}</yellow> - <level>{message}</level>"
    FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {extra[trace_id]} | {extra[type]} - {message}"


def _remove_logging_logger():
    """清除 uvicorn 等第三方库的默认 handler"""
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.error").handlers = []
    logging.getLogger("uvicorn").handlers = []


# --- 过滤器定义 ---

def filter_default(record: Any) -> bool:
    """通道 A: 只收 default"""
    return record["extra"].get("type") == "default"


# --- 全局状态管理 ---
_REGISTERED_TYPES: Set[str] = set()


def _init_logger(write_to_file: bool = True, write_to_console: bool = True):
    """初始化日志系统"""
    global _REGISTERED_TYPES

    loguru_logger = loguru.logger
    loguru_logger.remove()
    _REGISTERED_TYPES.clear()

    # 1. 默认配置 (type='default')
    loguru_logger.configure(extra={"trace_id": "-", "type": "default"})

    # 2. 控制台输出
    if write_to_console:
        loguru_logger.add(
            sink=sys.stderr,
            format=LogConfig.CONSOLE_FORMAT,
            level=LogConfig.LEVEL,
            enqueue=True,
            colorize=True,
            diagnose=True
        )

    # 3. 文件输出 (系统启动时只注册 default)
    if write_to_file:
        try:
            LogConfig.DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        # --- Sink A: 静态默认日志 ---
        loguru_logger.add(
            sink=LogConfig.DEFAULT_DIR / "app_{time:YYYY-MM-DD}.log",
            format=LogConfig.FILE_FORMAT,
            level=LogConfig.LEVEL,
            rotation=LogConfig.ROTATION,
            retention=LogConfig.RETENTION,
            compression=LogConfig.COMPRESSION,
            enqueue=True,
            serialize=True,
            filter=filter_default
        )

        _REGISTERED_TYPES.add("default")

    loguru_logger.info("Logger initialized.")
    return loguru_logger


# --- 初始化主对象 ---
logger = _init_logger()


# --- 动态注册函数 (已修改) ---

def get_logger_by_dynamic_type(log_type: str):
    """
    获取指定类型的 logger。
    如果是首次遇到该 log_type，会自动注册一个新的 Sink。
    """
    global _REGISTERED_TYPES

    if log_type in _REGISTERED_TYPES:
        return logger.bind(type=log_type)

    # --- 动态注册新 Sink ---

    # 定义闭包过滤器
    def specific_filter(record):
        return record["extra"].get("type") == log_type

    sink_path = LogConfig.BASE_LOG_DIR / log_type / "{time:YYYY-MM-DD}.log"

    try:
        (LogConfig.BASE_LOG_DIR / log_type).mkdir(parents=True, exist_ok=True)

        logger.add(
            sink=sink_path,
            format=LogConfig.FILE_FORMAT,
            level=LogConfig.LEVEL,
            rotation=LogConfig.ROTATION,
            retention=LogConfig.RETENTION,
            compression=LogConfig.COMPRESSION,
            enqueue=True,
            serialize=True,
            filter=specific_filter
        )

        _REGISTERED_TYPES.add(log_type)

        # [修改点]：使用 logger 记录系统事件
        # 这条日志本身带有 type='default'，所以会被 filter_default 捕获，
        # 写入到 /logs/default/app_xxxx.log 中
        logger.info(f"System: Registered new log sink for type {log_type}")

    except Exception as e:
        # [修改点]：使用 logger.error 记录错误
        # 同样写入默认日志，方便排查为什么文件夹创建失败
        logger.error(f"System: Failed to register sink for {log_type}. Error: {e}")
        return logger.bind(type="default")

    return logger.bind(type=log_type)
