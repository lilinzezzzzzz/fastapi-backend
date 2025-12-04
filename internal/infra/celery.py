import asyncio

from celery import Celery
from celery.schedules import crontab

from internal.config.setting import setting
from internal.infra.database import init_db, close_db
from internal.infra.redis import init_redis, close_redis
from pkg.celery_task import CeleryClient
from pkg.logger_tool import logger

# =========================================================
# 1. 基础配置定义
# =========================================================

# 需要加载的任务模块 (Python 模块路径)
CELERY_INCLUDE_MODULES = [
    "internal.aps_tasks.tasks",
]

# 任务路由配置 (决定任务去哪个队列)
CELERY_TASK_ROUTES = {
    # 定时任务统一走 cron_queue
    "internal.aps_tasks.*": {"queue": "cron_queue"},
    # 视频转码走高优先级队列
    "internal.business.video.transcode": {"queue": "video_queue", "priority": 10},
}

# 静态定时任务表 (Beat Schedule)
# 注意：Key 是任务的唯一标识，Value 中的 'task' 必须与 @task(name=...) 一致
STATIC_BEAT_SCHEDULE = {
    # 案例 1：Cron 风格 - 每隔 15 分钟执行一次
    "task_sum_every_15_min": {
        "task": "math.number_sum",
        "schedule": crontab(minute="*/15"),
        "args": (10, 20),
    },
    # 案例 2：Cron 风格 - 每天早上 8:30 执行
    "task_daily_report_morning": {
        "task": "math.number_sum",
        "schedule": crontab(hour=8, minute=30),
        "kwargs": {"x": 100, "y": 200},
    },
    # 案例 3：Interval 风格 - 每 30 秒执行一次
    "task_heartbeat_30s": {
        "task": "math.number_sum",
        "schedule": 30.0,
        "args": (1, 1),
    }
}


# =========================================================
# 2. Worker 生命周期钩子 (资源管理)
# =========================================================

def _worker_startup():
    """
    [Startup Hook] Worker 进程启动时执行：初始化 DB 和 Redis 连接池
    """
    logger.info(">>> Worker Process Starting: Initializing resources...")
    try:
        init_db()
        init_redis()
        logger.info("<<< Worker Process Resources Initialized.")
    except Exception as e:
        logger.critical(f"Worker resource initialization failed: {e}")
        raise e


async def _worker_shutdown():
    """
    [Shutdown Hook] Worker 进程关闭时执行：释放资源
    """
    logger.info(">>> Worker Process Stopping: Releasing resources...")
    try:
        # 并发关闭 DB 和 Redis，加快关闭速度
        await asyncio.gather(
            close_redis(),
            close_db(),
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"Error during resource shutdown: {e}")
    logger.info("<<< Worker Process Resources Released.")


# =========================================================
# 3. 实例化 Celery 客户端 (Global Singleton)
# =========================================================

# 必须在模块层级直接实例化，确保 'celery -A ...' 命令行能找到
celery_client = CeleryClient(
    app_name="my_fastapi_server",
    broker_url=setting.redis_url,
    backend_url=setting.redis_url,

    # 注册模块与路由
    include=CELERY_INCLUDE_MODULES,
    task_routes=CELERY_TASK_ROUTES,
    task_default_queue="default",

    # 注入静态定时任务配置 (之前漏了这里)
    beat_schedule=STATIC_BEAT_SCHEDULE,

    # 基础配置
    timezone="Asia/Shanghai"
)

# 注册生命周期钩子
celery_client.register_worker_hooks(
    on_startup=_worker_startup,
    on_shutdown=_worker_shutdown
)

# 导出原生 App 对象供 Celery CLI 使用
celery_app: Celery = celery_client.app


# =========================================================
# 4. FastAPI 集成辅助函数
# =========================================================

def init_celery():
    """
    在 FastAPI Lifespan 中调用。
    用于检查配置加载情况，或测试 Broker 连通性。
    """
    logger.info("Initializing Celery integration...")
    logger.info(f"Celery Modules Included: {CELERY_INCLUDE_MODULES}")

    # 调试模式下可打印路由表
    # logger.debug(f"Celery Routes: {CELERY_TASK_ROUTES}")

    try:
        # 主动检测 Broker 连接 (Health Check)
        with celery_app.connection_or_acquire() as conn:
            conn.ensure_connection(max_retries=1)
        logger.info(f"Celery Broker ({setting.redis_url}) connected successfully.")
    except Exception as e:
        # 即使连不上也不要阻断 API 启动，只是记录错误，因为 Worker 是独立进程
        logger.error(f"Celery Broker connection failed: {e}")

# =========================================================
# 启动命令说明
# =========================================================
# 1. 启动 Worker (执行任务):
# celery -A internal.infra.celery.celery_app worker -l info
#
# 2. 启动 Beat (派发定时任务):
# celery -A internal.infra.celery.celery_app beat -l info
