import logging
import os
import sys
from pathlib import Path
from typing import Any

import loguru

from pkg import BASE_DIR


class LogConfig:
    """日志配置中心"""
    LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # 基础日志目录
    BASE_LOG_DIR: Path = BASE_DIR / "logs"

    # 各分类日志子目录
    DEFAULT_DIR: Path = BASE_LOG_DIR / "default"
    LLM_DIR: Path = BASE_LOG_DIR / "llm"

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
def filter_llm(record: dict[str, Any]) -> bool:
    """只保留 type 为 llm 的日志"""
    return record["extra"].get("type") == "llm"


def filter_default(record: dict[str, Any]) -> bool:
    """保留 type 为 default 或者没有 type 标记的日志 (排除 llm)"""
    log_type = record["extra"].get("type")
    return log_type == "default"


def _init_logger(write_to_file: bool = True, write_to_console: bool = True):
    loguru_logger = loguru.logger
    loguru_logger.remove()

    # 1. 初始化默认 extra 字段
    loguru_logger.configure(extra={"trace_id": "-", "type": "default"})

    # 2. 配置控制台输出 (输出所有类型日志)
    if write_to_console:
        loguru_logger.add(
            sink=sys.stderr,
            format=LogConfig.CONSOLE_FORMAT,
            level=LogConfig.LEVEL,
            enqueue=True,
            colorize=True,
            diagnose=True
        )

    # 3. 配置文件输出
    if write_to_file:
        # 创建所有必要的目录
        for path in [LogConfig.DEFAULT_DIR, LogConfig.LLM_DIR]:
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                print(f"Failed to create log directory {path}: {e}", file=sys.stderr)

        # --- Sink A: 系统默认日志 (排除 LLM) ---
        loguru_logger.add(
            sink=LogConfig.DEFAULT_DIR / "app_{time:YYYY-MM-DD}.log",
            format=LogConfig.FILE_FORMAT,
            level=LogConfig.LEVEL,
            rotation=LogConfig.ROTATION,
            retention=LogConfig.RETENTION,
            compression=LogConfig.COMPRESSION,
            enqueue=True,
            filter=filter_default  # <--- 关键：使用过滤器
        )

        # --- Sink B: LLM 专用日志 ---
        loguru_logger.add(
            sink=LogConfig.LLM_DIR / "llm_{time:YYYY-MM-DD}.log",
            format=LogConfig.FILE_FORMAT,
            level=LogConfig.LEVEL,
            rotation=LogConfig.ROTATION,
            retention=LogConfig.RETENTION,
            compression=LogConfig.COMPRESSION,
            enqueue=True,
            filter=filter_llm  # <--- 关键：使用过滤器
        )

    loguru_logger.info(f"Logger initialized. Mode: Console={write_to_console}, File={write_to_file}")
    return loguru_logger


# 初始化主 Logger
logger = _init_logger()

# --- 关键：导出专用 Logger ---
# 在业务代码中，直接引入 llm_logger 即可写入 /logs/llm 目录
llm_logger = logger.bind(type="llm")
