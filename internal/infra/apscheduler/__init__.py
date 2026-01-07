from internal.infra.apscheduler.register import _register_tasks
from pkg.async_apscheduler import ApsSchedulerManager
from pkg.toolkit.logger import logger
from pkg.toolkit.types import LazyProxy

_apscheduler_manager: ApsSchedulerManager | None = None


def init_apscheduler():
    global _apscheduler_manager
    logger.info("Initializing APScheduler...")
    if _apscheduler_manager is not None:
        logger.warning("APScheduler has already been initialized.")
    else:
        _apscheduler_manager: ApsSchedulerManager = ApsSchedulerManager(timezone="UTC", max_instances=50)

    _register_tasks()
    logger.info("APScheduler initialized successfully.")


def _get_apscheduler_manager() -> ApsSchedulerManager:
    if _apscheduler_manager is None:
        raise RuntimeError("APScheduler not initialized. Call init_apscheduler() first.")
    return _apscheduler_manager


apscheduler_manager = LazyProxy[ApsSchedulerManager](_get_apscheduler_manager)
