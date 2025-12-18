import datetime
import time
from collections.abc import AsyncGenerator, Callable
from functools import wraps
from typing import Any

from pkg.async_logger import logger


def format_iso_string(val: datetime.datetime, *, use_z: bool = False) -> str:
    """
    将 datetime 对象格式化为 ISO 8601 字符串。
    - 有时区信息：保留时区并输出 ISO 格式
    - 无时区信息：假定为 UTC

    Args:
        val: 要格式化的 datetime 对象。
        use_z: 如果为 True 且时区为 UTC，输出 'Z' 格式；否则输出 '+00:00' 格式。

    Returns:
        ISO 8601 格式的字符串。
    """
    if val.tzinfo is None:
        val = val.replace(tzinfo=datetime.UTC)

    if use_z and val.utcoffset() == datetime.timedelta(0):
        return val.strftime("%Y-%m-%dT%H:%M:%SZ")

    return val.isoformat()


def parse_iso_datetime(iso_string: str) -> datetime.datetime:
    """
    将 ISO 8601 格式的时间字符串解析为 datetime 对象。

    Args:
        iso_string: ISO 格式的时间字符串（例如 "2024-12-23T18:30:00Z" 或 "2024-12-23T18:30:00+00:00"）

    Returns:
        解析后的 datetime 对象。

    Raises:
        ValueError: 当字符串格式无效时。
    """
    try:
        return datetime.datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"Invalid ISO format string: {iso_string}") from e


def convert_to_utc(val: datetime.datetime) -> datetime.datetime:
    """
    将 datetime 转换为带 UTC 时区信息的 datetime。
    - 有时区信息：转换为 UTC
    - 无时区信息：假定已经是 UTC，直接添加时区标记

    Args:
        val: 要转换的 datetime 对象。

    Returns:
        带 UTC 时区信息的 datetime 对象。
    """
    if val.tzinfo is None:
        # naive datetime 假定为 UTC
        return val.replace(tzinfo=datetime.UTC)
    return val.astimezone(datetime.UTC)


def get_utc_timestamp() -> int:
    return int(datetime.datetime.now(tz=datetime.UTC).timestamp())


def utc_now_naive() -> datetime.datetime:
    """
    获取当前 UTC 时间，不带时区信息（naive datetime），精度到秒。
    """
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0, tzinfo=None)


def async_generator_timer(slow_threshold: float = 5.0):
    """
    异步生成器计时装饰器，用于统计 Handler.handle 方法或普通异步生成器函数的执行时间。

    Args:
        slow_threshold: 慢执行阈值（秒），超过此时间会记录警告日志

    Usage:
        @async_generator_timer(slow_threshold=5.0)
        async def handle(self, messages, **kwargs):
            ...
    """

    def decorator(func: Callable[..., AsyncGenerator[Any, None]]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 支持类方法和普通函数
            if args and hasattr(args[0], "__class__"):
                handler_name = f"{args[0].__class__.__name__}.{func.__name__}"
            else:
                handler_name = func.__name__

            start_time = time.perf_counter()

            logger.info(f"Starting {handler_name}...")
            try:
                async for response in func(*args, **kwargs):
                    yield response
            finally:
                elapsed = time.perf_counter() - start_time
                if elapsed > slow_threshold:
                    logger.info(f"SLOW: {handler_name} took {elapsed:.3f}s (threshold: {slow_threshold}s)")
                else:
                    logger.info(f"Completed {handler_name} in {elapsed:.3f}s")

        return wrapper

    return decorator
