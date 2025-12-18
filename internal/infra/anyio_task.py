from internal.core.logger import logger
from pkg.anyio_task import AnyioTaskHandler

anyio_task_manager: AnyioTaskHandler | None = None


async def init_anyio_task_handler():
    global anyio_task_manager
    logger.info("Init anyio task manager...")
    if anyio_task_manager is not None:
        logger.warning("Anyio task manager has been initialized.")
        return

    anyio_task_manager = AnyioTaskHandler()
    await anyio_task_manager.start()
    logger.info("Init anyio task manager completed.")


async def close_anyio_task_handler():
    global anyio_task_manager
    logger.info("Stop anyio task manager...")
    if anyio_task_manager is None:
        logger.warning("Anyio task manager has not been initialized.")
        return

    await anyio_task_manager.shutdown()
    anyio_task_manager = None
    logger.info("Stop anyio task manager completed.")
