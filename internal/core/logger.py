from datetime import timezone, time, timedelta
from pathlib import Path

import loguru

from internal import BASE_DIR
from pkg.loguru_logger import LoggerManager, RotationType, RetentionType, logger as default_logger

logger_manager: LoggerManager | None = None
logger: loguru.Logger | None = None


def init_logger(
        *,
        level: str = "INFO",
        base_log_dir: Path | None = None,
        rotation: RotationType = time(0, 0, 0, tzinfo=timezone.utc),
        retention: RetentionType = timedelta(days=30),
        use_utc: bool = True,
        enqueue: bool = True
):
    global logger_manager, logger
    default_logger.info("Initializing logger...")
    logger_manager = LoggerManager(
        level=level,
        base_log_dir=base_log_dir or BASE_DIR / "logs",
        rotation=rotation,
        retention=retention,
        use_utc=use_utc,
        enqueue=enqueue,
    )
    logger = logger_manager.setup()
    default_logger.info("Logger initialized.")
