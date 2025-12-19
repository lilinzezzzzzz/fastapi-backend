from internal.tasks.apscheduler.tasks import number_sum
from pkg.async_apscheduler import ApsSchedulerManager
from pkg.async_logger import logger
from pkg.toolkit.types import LazyProxy

_apscheduler_manager: ApsSchedulerManager | None = None


def init_apscheduler():
    global _apscheduler_manager
    logger.info("Initializing APScheduler...")
    if _apscheduler_manager is not None:
        logger.warning("APScheduler has already been initialized.")
    else:
        _apscheduler_manager: ApsSchedulerManager = ApsSchedulerManager(timezone="UTC", max_instances=50)

    _apscheduler_manager.register_cron(number_sum, cron_kwargs={"minute": "*/15", "second": 0})
    logger.info("APScheduler initialized successfully.")


def _get_apscheduler_manager() -> ApsSchedulerManager:
    if _apscheduler_manager is None:
        raise RuntimeError("APScheduler not initialized. Call init_apscheduler() first.")
    return _apscheduler_manager


apscheduler_manager = LazyProxy(_get_apscheduler_manager)
