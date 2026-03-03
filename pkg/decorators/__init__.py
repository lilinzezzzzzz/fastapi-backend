"""通用装饰器模块

提供异步生成器计时等装饰器。
此模块不依赖项目日志，默认使用标准库 logging。
"""

import logging
import time
from collections.abc import AsyncGenerator, Callable
from functools import wraps
from typing import Any

from loguru import Logger as LoguruLogger

# 默认日志器（标准库）
_default_logger = logging.getLogger(__name__)

# 支持的日志器类型
LoggerType = logging.Logger | LoguruLogger


def async_generator_timer(
    slow_threshold: float = 5.0,
    *,
    logger: LoggerType | None = None,
):
    """
    异步生成器计时装饰器，用于统计 Handler.handle 方法或普通异步生成器函数的执行时间。

    Args:
        slow_threshold: 慢执行阈值（秒），超过此时间会记录警告日志
        logger: 可选的日志器实例，默认使用标准库 logging

    Examples:
        # 使用默认标准库 logging
        @async_generator_timer()
        async def handle(): ...

        # 注入项目日志
        from pkg.logger import logger as app_logger
        @async_generator_timer(logger=app_logger)
        async def handle(): ...
    """
    _logger = logger or _default_logger

    def decorator(func: Callable[..., AsyncGenerator[Any, None]]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 支持类方法和普通函数
            if args and hasattr(args[0], "__class__"):
                handler_name = f"{args[0].__class__.__name__}.{func.__name__}"
            else:
                handler_name = func.__name__

            start_time = time.perf_counter()

            _logger.info(f"Starting {handler_name}...")
            try:
                async for response in func(*args, **kwargs):
                    yield response
            finally:
                elapsed = time.perf_counter() - start_time
                if elapsed > slow_threshold:
                    _logger.warning(f"SLOW: {handler_name} took {elapsed:.3f}s (threshold: {slow_threshold}s)")
                else:
                    _logger.info(f"Completed {handler_name} in {elapsed:.3f}s")

        return wrapper

    return decorator
