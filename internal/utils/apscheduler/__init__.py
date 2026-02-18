from pkg.logger import logger
from pkg.toolkit.apscheduler import ApsSchedulerManager
from pkg.toolkit.types import lazy_proxy

_apscheduler_manager: ApsSchedulerManager | None = None


def init_apscheduler():
    global _apscheduler_manager
    logger.info("Initializing APScheduler...")
    if _apscheduler_manager is not None:
        logger.warning("APScheduler has already been initialized.")
        return

    _apscheduler_manager = ApsSchedulerManager(timezone="UTC", max_instances=50)
    _register_tasks(_apscheduler_manager)
    logger.info("APScheduler initialized successfully.")


def _register_tasks(manager: ApsSchedulerManager):
    """注册定时任务"""
    from internal.utils.apscheduler.tasks import handle_number_sum

    manager.register_cron(handle_number_sum, cron_kwargs={"minute": "*/15", "second": 0})


def _get_apscheduler_manager() -> ApsSchedulerManager:
    if _apscheduler_manager is None:
        raise RuntimeError("APScheduler not initialized. Call init_apscheduler() first.")
    return _apscheduler_manager


apscheduler_manager = lazy_proxy(_get_apscheduler_manager)
