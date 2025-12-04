import asyncio

from celery import Celery
from celery.schedules import crontab

from internal.config.setting import setting
from internal.infra.database import init_db, close_db
from internal.infra.redis import init_redis, close_redis
from pkg.celery_task import CeleryClient
from pkg.logger_tool import logger

# 1. 定义模块
CELERY_INCLUDE_MODULES = [
    "internal.apscheduler.tasks",
]

# 2. 定义路由
CELERY_TASK_ROUTES = {
    "internal.apscheduler.*": {"queue": "cron_queue"},
    "internal.business.video.transcode": {"queue": "video_queue", "priority": 10},
}

# =========================================================
# 定义静态定时任务表
# =========================================================
STATIC_BEAT_SCHEDULE = {
    # 案例 1：Cron 风格 - 每隔 15 分钟执行一次
    "task_sum_every_15_min": {
        "task": "math.number_sum",  # 必须与 @task(name=...) 中的名字完全一致
        "schedule": crontab(minute="*/15"),
        "args": (10, 20),  # 位置参数 (x, y)
    },

    # 案例 2：Cron 风格 - 每天早上 8:30 执行
    "task_daily_report_morning": {
        "task": "math.number_sum",
        "schedule": crontab(hour=8, minute=30),
        "kwargs": {"x": 100, "y": 200},  # 关键字参数
    },

    # 案例 3：Interval 风格 - 每 30 秒执行一次
    "task_heartbeat_30s": {
        "task": "math.number_sum",
        "schedule": 30.0,  # 直接写数字，单位为秒
        "args": (1, 1),
    }
}


# =========================================================
# 3. 定义聚合函数 (Wrapper Functions)
# =========================================================

def _worker_startup():
    """
    聚合启动钩子：按顺序初始化所有资源
    """
    logger.info(">>> Worker Process Starting: Initializing resources...")

    # 1. 初始化 DB
    init_db()

    # 2. 初始化 Redis
    init_redis()

    logger.info("<<< Worker Process Resources Initialized.")


async def _worker_shutdown():
    """
    聚合关闭钩子：关闭所有资源
    """
    logger.info(">>> Worker Process Stopping: Releasing resources...")

    # 方式 A：顺序关闭 (简单稳健)
    # await close_redis()
    # await close_db()

    # 方式 B：并发关闭 (推荐，速度更快)
    # 使用 asyncio.gather 同时关闭 DB 和 Redis，节省时间
    try:
        await asyncio.gather(
            close_redis(),
            close_db(),
            return_exceptions=True  # 防止其中一个报错影响另一个
        )
    except Exception as e:
        logger.error(f"Error during resource shutdown: {e}")

    logger.info("<<< Worker Process Resources Released.")


# 3. 【关键】立即实例化 (Global Scope)
# 必须在模块层级直接赋值，否则 'celery -A ...' 命令行找不到它
celery_client = CeleryClient(
    app_name="my_fastapi_server",
    broker_url=setting.redis_url,
    backend_url=setting.redis_url,

    include=CELERY_INCLUDE_MODULES,
    task_routes=CELERY_TASK_ROUTES,
    task_default_queue="default",

    timezone="Asia/Shanghai"
)

celery_client.register_worker_hooks(
    on_startup=_worker_startup,  # 传入聚合后的启动函数
    on_shutdown=_worker_shutdown  # 传入聚合后的关闭函数
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


"""
启动 Worker (负责真正执行任务):
celery -A internal.infra.celery.celery_app worker -l info

启动 Beat (负责按时间派发任务):
celery -A internal.infra.celery.celery_app beat -l info
"""
