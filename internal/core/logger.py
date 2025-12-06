from datetime import timezone, time, timedelta
from pathlib import Path

import loguru

from pkg.logger_tool import LoggerManager, RotationType, RetentionType

logger_manager: LoggerManager | None = None
logger: loguru.Logger | None = None
get_dynamic_logger = None


def init_logger(
        *,
        level: str = "INFO",
        base_log_dir: Path | None = None,
        rotation: RotationType = time(0, 0, 0, tzinfo=timezone.utc),
        retention: RetentionType = timedelta(days=30),
        compression: str | None = None,
        use_utc: bool = True,
        enqueue: bool = True,
):
    global logger_manager, logger, get_dynamic_logger
    logger_manager = LoggerManager(
        level=level,
        base_log_dir=base_log_dir,
        rotation=rotation,
        retention=retention,
        compression=compression,
        use_utc=use_utc,
        enqueue=enqueue,
    )
    logger = logger_manager.setup()
    get_dynamic_logger = logger_manager.get_dynamic_logger
