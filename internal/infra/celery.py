from celery import Celery
from internal.config.setting import setting
from pkg.celery_task_manager import CeleryClient
from pkg.logger_tool import logger

# 1. 定义模块
CELERY_INCLUDE_MODULES = [
    "internal.aps_tasks.tasks",
]

# 2. 定义路由
CELERY_TASK_ROUTES = {
    "internal.aps_tasks.*": {"queue": "cron_queue"},
    "internal.business.video.transcode": {"queue": "video_queue", "priority": 10},
}

# 3. 【关键】立即实例化 (Global Scope)
# 必须在模块层级直接赋值，否则 'celery -A ...' 命令行找不到它
celery_client = CeleryClient(
    app_name="my_fastapi_server",
    broker_url=setting.redis_url,
    backend_url=setting.redis_url,

    include=CELERY_INCLUDE_MODULES,
    task_routes=CELERY_TASK_ROUTES,
    task_default_queue="default",

    timezone="Asia/Shanghai",
    redbeat_redis_url=setting.redis_url,
)

# 导出这个对象给 Celery CLI 使用
celery_app: Celery = celery_client.app


def ping_celery():
    """
    这个函数依然保留，但在 Lifespan 中调用。
    它的作用不再是'创建对象'，而是'检查连接'或'打印日志'。
    """
    logger.info("Checking Celery Configuration...")

    # 打印路由信息用于调试
    logger.info(f"Celery Routes: {CELERY_TASK_ROUTES}")
    logger.info(f"Celery Include: {CELERY_INCLUDE_MODULES}")

    try:
        # 可选：在 FastAPI 启动时主动 Ping 一下 Redis
        # 如果 Redis 没通，这里会抛出异常，让你在 API 启动阶段就知道有问题
        with celery_app.connection_or_acquire() as conn:
            conn.ensure_connection(max_retries=1)
        logger.info(f"Celery Broker connected successfully.")
    except Exception as e:
        # 视情况决定是否要抛出异常阻断启动
        logger.error(f"Celery Broker connection warning: {e}")
