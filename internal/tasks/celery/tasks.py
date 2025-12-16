import asyncio

from internal.infra.celery import celery_client
from internal.tasks.task_handlers import handle_number_sum, handle_scheduled_sum
from pkg.async_logger import logger


async def func(): ...


# 使用我们封装的 client.app 获取原生 app 装饰器
@celery_client.app.task(bind=True, name="internal.apscheduler.tasks.number_sum")
def number_sum(self, x: int, y: int):
    """
    示例异步任务任务
    """
    try:
        # 调用共享的异步任务处理函数
        result = asyncio.run(handle_number_sum(x, y))
        return result
    except Exception as e:
        logger.error(f"Task failed: {e}")
        # 任务重试逻辑
        raise self.retry(exc=e, countdown=5, max_retries=3)


@celery_client.app.task(bind=True, name="task_sum_every_15_min")
def task_sum_every_15_min(self, x: int, y: int):
    """
    示例静态定时任务任务
    """
    try:
        # 调用共享的异步任务处理函数
        result = asyncio.run(handle_scheduled_sum(x, y))
        return result
    except Exception as e:
        logger.error(f"Task failed: {e}")
        raise self.retry(exc=e, countdown=5, max_retries=3)
