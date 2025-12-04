from internal.aps_tasks.tasks import number_sum
from internal.constants import REDIS_KEY_LOCK_PREFIX
from internal.infra.redis import get_cache_client
from pkg.aps_task_manager import ApsSchedulerManager, new_aps_scheduler_tool
from pkg.cache.client import CacheClient
from pkg.logger_tool import logger

_apscheduler_manager: ApsSchedulerManager | None = None


def init_apscheduler():
    global _apscheduler_manager
    logger.info("Initializing APScheduler...")
    if _apscheduler_manager is not None:
        return

    _apscheduler_manager: ApsSchedulerManager = new_aps_scheduler_tool(timezone="UTC", max_instances=50)
    _apscheduler_manager.register_cron_job(
        number_sum,
        cron_kwargs={"minute": "*/15", "second": 0}
    )
    logger.info("APScheduler initialized successfully.")


async def start_apscheduler(pid: int):
    logger.info(f"Current process {pid} acquired apscheduler master lock, starting APScheduler")
    if _apscheduler_manager is None:
        raise Exception("APScheduler is not initialized. Call init_apscheduler() first.")

    scheduler_lock_key = f"{REDIS_KEY_LOCK_PREFIX}:apscheduler:master"
    # 只有一个 worker 能获得锁，成为 apscheduler master
    cache_client: CacheClient = get_cache_client()
    lock_id = await cache_client.acquire_lock(
        scheduler_lock_key,
        expire_ms=180000,  # 3 分钟, 避免锁死
        timeout_ms=1000,  # 最多等 1 秒获取锁
        retry_interval_ms=200  # 可略调
    )
    if lock_id:
        _apscheduler_manager.start()
        return True
    else:
        logger.info(f"Current process {pid} did not acquire apscheduler master lock, skipping apscheduler")
        return False


async def shutdown_apscheduler(pid: int):
    logger.info(f"Current process {pid} Shutting down APScheduler...")
    if _apscheduler_manager is None:
        raise Exception("APScheduler is not initialized. Call init_apscheduler() first.")

    await _apscheduler_manager.shutdown()
    logger.info(f"Current process {pid} Shutting down APScheduler successfully")
