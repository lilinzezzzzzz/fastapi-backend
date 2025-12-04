from internal.infra.celery import celery_client
from pkg.logger_tool import logger

# 使用我们封装的 client.app 获取原生 app 装饰器
@celery_client.app.task(bind=True, name="internal.aps_tasks.tasks.number_sum")
def number_sum(self, x: int, y: int):
    """
    示例任务
    """
    try:
        logger.info(f"Task number_sum started: {x} + {y}")
        result = x + y
        return result
    except Exception as e:
        logger.error(f"Task failed: {e}")
        # 任务重试逻辑
        raise self.retry(exc=e, countdown=5, max_retries=3)
