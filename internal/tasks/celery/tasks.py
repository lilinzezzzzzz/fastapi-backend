from internal.infra.celery import celery_client
from pkg.logger_tool import logger


# 使用我们封装的 client.app 获取原生 app 装饰器
@celery_client.app.task(bind=True, name="internal.apscheduler.tasks.number_sum")
def number_sum(self, x: int, y: int):
    """
    示例异步任务任务
    """
    try:
        logger.info(f"Task number_sum started: {x} + {y}")
        result = x + y
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
        logger.info(f"Task task_sum_every_15_min started: {x} + {y}")
        result = x + y
        logger.info(f"Task task_sum_every_15_min completed: {result}")
    except Exception as e:
        logger.error(f"Task failed: {e}")
        raise self.retry(exc=e, countdown=5, max_retries=3)
