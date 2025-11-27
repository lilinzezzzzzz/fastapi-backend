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

    # 基础日志根目录
    BASE_LOG_DIR: Path = BASE_DIR / "logs"

    # 只有 Default 是静态定义的，其他目录(llm/device等)都是动态生成的
    DEFAULT_DIR: Path = BASE_LOG_DIR / "default"

    FILE_NAME: str = "{time:YYYY-MM-DD}.log"
    ROTATION: str = os.getenv("LOG_ROTATION", "00:00")
    RETENTION: str = os.getenv("LOG_RETENTION", "30 days")
    COMPRESSION: str = "zip"

    # 格式配置
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
# 用于记录已注册的 type，防止重复 add sink
_REGISTERED_TYPES: Set[str] = set()


def _init_logger(write_to_file: bool = True, write_to_console: bool = True):
    """初始化日志系统"""
    global _REGISTERED_TYPES

    loguru_logger = loguru.logger
    loguru_logger.remove()

    # 重置已注册列表 (测试隔离用)
    _REGISTERED_TYPES.clear()

    # 1. 默认配置
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
            filter=filter_default
        )

        # 标记 default 为已注册
        _REGISTERED_TYPES.add("default")

    loguru_logger.info("Logger initialized.")
    return loguru_logger


# --- 初始化主对象 ---
logger = _init_logger()


# --- 动态注册函数 ---

def get_logger_by_type(log_type: str):
    """
    获取指定类型的 logger。
    如果是首次遇到该 log_type (例如 'llm', 'device_01')，会自动注册一个新的 Sink。

    :param log_type: 业务类型或设备ID
    """
    global _REGISTERED_TYPES

    # 1. 如果已经注册过，直接返回绑定好的 logger
    if log_type in _REGISTERED_TYPES:
        return logger.bind(type=log_type)

    # 2. 动态注册新 Sink
    # 定义闭包过滤器：只接收当前 log_type 的日志
    def specific_filter(record):
        return record["extra"].get("type") == log_type

    # 路径构造：使用变量拼接，而不是 Loguru 的 {extra} 模板
    # 这样彻底规避了 KeyError: 'extra' 问题，且支持 Rotation
    sink_path = LogConfig.BASE_LOG_DIR / log_type / "{time:YYYY-MM-DD}.log"

    try:
        # 确保目录存在
        (LogConfig.BASE_LOG_DIR / log_type).mkdir(parents=True, exist_ok=True)

        logger.add(
            sink=sink_path,
            format=LogConfig.FILE_FORMAT,
            level=LogConfig.LEVEL,
            rotation=LogConfig.ROTATION,
            retention=LogConfig.RETENTION,
            compression=LogConfig.COMPRESSION,
            enqueue=True,  # 异步写入
            filter=specific_filter
        )

        _REGISTERED_TYPES.add(log_type)
        # 仅在调试时打开，生产环境可注释
        # print(f"DEBUG: Registered new log sink for type: {log_type}", file=sys.stderr)

    except Exception as e:
        print(f"Error registering sink for {log_type}: {e}", file=sys.stderr)

    # 3. 返回绑定了新类型的 logger
    return logger.bind(type=log_type)
