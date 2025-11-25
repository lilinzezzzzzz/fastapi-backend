import logging
import os
import sys
from pathlib import Path

import loguru

from pkg import BASE_DIR


class LogConfig:
    """日志配置中心"""
    LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    DIR: Path = BASE_DIR / "logs"
    FILE_NAME: str = "app_{time:YYYY-MM-DD}.log"
    ROTATION: str = os.getenv("LOG_ROTATION", "00:00")  # 支持大小/时间轮转
    RETENTION: str = os.getenv("LOG_RETENTION", "30 days")
    COMPRESSION: str = "zip"  # 压缩格式


class LogFormat:
    """日志格式模板"""
    CONSOLE = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <magenta>{extra[trace_id]}</magenta> - <level>{message}</level>"

    FILE = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {extra[trace_id]} - {message}"


def _remove_logging_logger():
    # 清除uvicorn相关日志记录器的默认处理日志处理器
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.error").handlers = []
    logging.getLogger("uvicorn").handlers = []


def _init_logger(write_to_file: bool = False, write_to_console: bool = True):
    """
    初始化 Logger
    :param write_to_file: 是否写入文件 (True/False). 如果为 None，则非 local 环境默认为 True
    :param write_to_console: 是否写入 stderr (True/False). 如果为 None，则 local 环境默认为 True
    """
    loguru_logger = loguru.logger

    # 注意：由于还没有配置 sink，这里的 info 可能还只会输出到默认的 stderr，或者被暂时忽略，取决于 loguru 状态
    # 为了保险，通常建议配置完再打印 info，或者先保留默认 handle

    loguru_logger.remove()  # 移除所有默认处理器
    loguru_logger.configure(extra={"trace_id": "-"})

    # 3. 配置控制台输出 (sys.stderr)
    if write_to_console:
        loguru_logger.add(
            sink=sys.stderr,
            format=LogFormat.CONSOLE,
            level=LogConfig.LEVEL,
            enqueue=True,  # 建议在异步环境开启
            colorize=True,
            diagnose=True
        )

    # 4. 配置文件输出
    if write_to_file:
        # 只有需要写文件时，才尝试创建目录，避免在无权限的容器环境中报错
        try:
            LogConfig.DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            # 这里可以用 print，因为 logger 可能还没配置好文件输出，或者 stderr 被关了
            print(f"Failed to create log directory: {e}", file=sys.stderr)
            sys.exit(1)

        loguru_logger.add(
            sink=LogConfig.DIR / LogConfig.FILE_NAME,
            format=LogFormat.FILE,
            level=LogConfig.LEVEL,
            rotation=LogConfig.ROTATION,
            retention=LogConfig.RETENTION,
            compression=LogConfig.COMPRESSION,
            diagnose=True,  # 生产环境通常建议设为 False 以防泄漏敏感信息，视情况而定
            enqueue=True
        )

    loguru_logger.info(f"Init logger successfully. (Console: {write_to_console}, File: {write_to_file})")
    return loguru_logger


logger = _init_logger()
