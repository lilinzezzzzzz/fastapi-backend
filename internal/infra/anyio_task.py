from pkg.anyio_task import AnyioTaskManager
from pkg.logger_tool import logger

anyio_task_manager: AnyioTaskManager | None = None


def init_anyio_task_manager():
    global anyio_task_manager
    logger.info("Init anyio task manager...")
    if anyio_task_manager is not None:
        logger.warning("Anyio task manager has been initialized.")
        return

    anyio_task_manager = AnyioTaskManager()
    logger.info("Init anyio task manager completed.")
