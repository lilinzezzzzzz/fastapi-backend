"""
任务处理函数模块
提供可被 Celery 和 APScheduler 复用的任务逻辑
"""

from pkg.async_logger import logger


async def handle_number_sum(x: int, y: int) -> int:
    """
    计算两个数字的和
    :param x: 数字1
    :param y: 数字2
    :return: 两个数字的和
    """
    logger.info(f"计算两个数字的和: {x} + {y}")
    result = x + y
    logger.info(f"计算结果: {result}")
    return result
