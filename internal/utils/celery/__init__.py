from collections.abc import Callable, Coroutine
from pathlib import Path

import anyio
from celery import Celery
from celery.schedules import crontab

from internal.config import settings
from internal.infra.database import close_async_db, init_async_db, reset_async_db
from internal.infra.redis import close_async_redis, init_async_redis, reset_async_redis
from pkg.logger import init_logger, logger
from pkg.toolkit import context
from pkg.toolkit.celery import CeleryClient

# =========================================================
# 1. 基础配置定义
# =========================================================

# 需要加载的任务模块 (Python 模块路径)
CELERY_INCLUDE_MODULES = [
    "internal.infra.celery.register",
]

# 任务路由配置 (决定任务去哪个队列)
CELERY_TASK_ROUTES = {
    # Celery 任务统一走 celery_queue
    "internal.infra.celery.register.*": {"queue": "celery_queue"},
    # 定时任务统一走 cron_queue
    "task_sum_every_15_min": {"queue": "cron_queue"},
}

# 静态定时任务表 (Beat Schedule)
# 注意：Key 是任务的唯一标识，Value 中的 'task' 必须与 @task(name=...) 一致
STATIC_BEAT_SCHEDULE = {
    # 案例 1：Cron 风格 - 每隔 15 分钟执行一次
    "task_sum_every_15_min": {
        "task": "internal.infra.celery.register.number_sum",
        "schedule": crontab(minute="*/15"),
        "args": (10, 20),
    },
    # 案例 2：Interval 风格 - 每 30 秒执行一次
    "task_heartbeat_30s": {
        "task": "internal.infra.celery.register.number_sum",
        "schedule": 30.0,
        "args": (1, 1),
    },
}


# =========================================================
# 2. Worker 生命周期钩子 (资源管理)
# =========================================================


def _worker_startup():
    """
    [Startup Hook] Worker 进程启动时执行：初始化 Logger、DB 和 Redis 连接池
    """
    # 1. 首先初始化 Logger (其他模块依赖它)
    init_logger(level="INFO", base_log_dir=Path("/temp/celery"))
    logger.info(">>> Worker Process Starting: Initializing resources...")
    try:
        # 2. 初始化数据库和 Redis
        init_async_db()
        init_async_redis()
        logger.success("Worker Process Resources Initialized successfully.")
    except Exception as e:
        logger.critical(f"Worker resource initialization failed: {e}")
        raise e


async def _worker_shutdown():
    """
    [Shutdown Hook] Worker 进程关闭时执行：释放资源
    """
    logger.warning("Worker Process Stopping: Releasing resources...")

    async def safe_close(close_func):
        try:
            await close_func()
        except Exception as e:
            logger.error(f"Error during resource shutdown: {e}")

    # 并发关闭 DB 和 Redis，加快关闭速度
    async with anyio.create_task_group() as tg:
        tg.start_soon(safe_close, close_async_redis)
        tg.start_soon(safe_close, close_async_db)

    logger.warning("Worker Process Resources Released.")


# =========================================================
# 3. 实例化 Celery 客户端 (Global Singleton)
# =========================================================

# 必须在模块层级直接实例化，确保 'celery -A ...' 命令行能找到
celery_client = CeleryClient(
    app_name="my_fastapi_server",
    broker_url=settings.redis_url,
    backend_url=settings.redis_url,
    # 注册模块与路由
    include=CELERY_INCLUDE_MODULES,
    task_routes=CELERY_TASK_ROUTES,
    beat_schedule=STATIC_BEAT_SCHEDULE,
)

# 注册生命周期钩子
celery_client.register_worker_hooks(on_startup=_worker_startup, on_shutdown=_worker_shutdown)

# 导出原生 App 对象供 Celery CLI 使用
celery_app: Celery = celery_client.app


# =========================================================
# 4. FastAPI 集成辅助函数
# =========================================================


def check_celery_health():
    """
    在 FastAPI Lifespan 中调用。
    用于检查配置加载情况，或测试 Broker 连通性。
    """
    logger.info("Initializing Celery integration...")
    logger.info(f"Celery Modules Included: {CELERY_INCLUDE_MODULES}")

    # 调试模式下可打印路由表
    logger.info(f"Celery Routes: {CELERY_TASK_ROUTES}")

    try:
        # 主动检测 Broker 连接 (Health Check)
        with celery_app.connection_or_acquire() as conn:
            conn.ensure_connection(max_retries=1)
        logger.info(f"Celery Broker ({settings.redis_url}) connected successfully.")
    except Exception as e:
        # 即使连不上也不要阻断 API 启动，只是记录错误，因为 Worker 是独立进程
        logger.error(f"Celery Broker connection failed: {e}")


def run_in_async[T](coro_func: Callable[[], Coroutine[None, None, T]], trace_id: str) -> T:
    """
    在 Celery 同步任务中执行异步代码。
    """

    # 1. 重置旧的连接池
    reset_async_db()
    reset_async_redis()

    # 2. 准备上下文
    context_kwargs: dict[str, str | int] = {
        "trace_id": trace_id,
    }

    async def _wrapper() -> T:
        # 1. 在新事件循环中初始化
        init_async_db()
        init_async_redis()

        # 2. 设置上下文
        context.init(**context_kwargs)

        with logger.contextualize(trace_id=trace_id):
            try:
                # 3. 执行业务逻辑 (通过闭包捕获 coro_func)
                return await coro_func()
            finally:
                # 4. 清理连接
                await close_async_db()
                await close_async_redis()

    return anyio.run(_wrapper)


"""
# =========================================================
# 启动命令说明（项目根目录执行）
# =========================================================
1. 启动任务
# 开发环境 - 基础启动
celery -A internal.infra.celery.initialization.celery_app worker -l info -c 1 -Q default,celery_queue

# 开发环境 - 指定并发数（容器资源有限时建议限制）
celery -A internal.infra.celery.initialization.celery_app worker -l info -c 2 -Q default,celery_queue

# 生产环境 - 推荐配置
celery -A internal.infra.celery.initialization.celery_app worker \
    -l info \
    -c 4 \
    --max-tasks-per-child 1000 \
    --max-memory-per-child 120000 \
    -Q default,celery_queue

# 2. 启动 Beat (派发定时任务):
# celery -A internal.infra.celery.initialization.celery_app beat -l info
"""
