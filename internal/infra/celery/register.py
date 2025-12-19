import anyio

from internal.infra.celery.initialization import celery_client
from internal.tasks.demo_task import handle_number_sum
from pkg.async_logger import logger


@celery_client.app.task(bind=True, name="internal.infra.celery.register.number_sum")
def number_sum(self, x: int | list[int], y: int):
    """
    示例异步任务任务
    支持处理单个数字加法，或 Chord 回调的列表求和
    """
    try:
        # --- 新增：兼容 Chord 回调逻辑 ---
        # 如果 x 是列表（来自 group/chord 的结果集），先进行聚合求和
        if isinstance(x, list):
            logger.info(f"Received list input from chord: {x}, aggregating...")
            x = sum(x)
        # ----------------------------------

        # 调用共享的异步任务处理函数
        result = anyio.run(handle_number_sum, x, y)
        return result
    except Exception as e:
        logger.error(f"Task failed: {e}")
        # 任务重试逻辑
        raise self.retry(exc=e, countdown=5, max_retries=3) from e
