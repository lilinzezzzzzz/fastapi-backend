from internal.tasks.apscheduler.tasks import number_sum
from pkg.aps_task import ApsSchedulerManager
from pkg.loguru_logger import logger

_apscheduler_manager: ApsSchedulerManager | None = None


def init_apscheduler():
    global _apscheduler_manager
    logger.info("Initializing APScheduler...")
    if _apscheduler_manager is not None:
        logger.warning("APScheduler has already been initialized.")
    else:
        _apscheduler_manager: ApsSchedulerManager = ApsSchedulerManager(timezone="UTC", max_instances=50)

    _apscheduler_manager.register_cron(
        number_sum,
        cron_kwargs={"minute": "*/15", "second": 0}
    )
    logger.info("APScheduler initialized successfully.")
