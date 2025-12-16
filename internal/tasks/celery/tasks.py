import anyio

from internal.infra.celery import celery_client
from internal.tasks.task_handlers import handle_number_sum
from pkg.async_logger import logger


# 使用我们封装的 client.app 获取原生 app 装饰器
@celery_client.app.task(bind=True, name="internal.celery.tasks.number_sum")
def number_sum(self, x: int, y: int):
    """
    示例异步任务任务
    """
    try:
        # 调用共享的异步任务处理函数
        result = anyio.run(handle_number_sum, x, y)
        return result
    except Exception as e:
        logger.error(f"Task failed: {e}")
        # 任务重试逻辑
        raise self.retry(exc=e, countdown=5, max_retries=3) from e
