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
    await anyio_task_manager.start()
    logger.info("Init anyio task manager completed.")


async def stop_anyio_task_manager():
    global anyio_task_manager
    logger.info("Stop anyio task manager...")
    if anyio_task_manager is None:
        logger.warning("Anyio task manager has not been initialized.")
        return

    await anyio_task_manager.shutdown()
    anyio_task_manager = None
    logger.info("Stop anyio task manager completed.")
