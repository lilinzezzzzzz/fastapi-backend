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
