from datetime import UTC, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from internal import BASE_DIR
from pkg.async_logger import LoggerManager, RetentionType, RotationType, logger as default_logger

if TYPE_CHECKING:
    from loguru import Logger

_logger_manager: LoggerManager | None = None
_logger: "Logger | None" = None


def init_logger(
    *,
    level: str = "INFO",
    base_log_dir: Path | None = None,
    rotation: RotationType = time(0, 0, 0, tzinfo=UTC),
    retention: RetentionType = timedelta(days=30),
    use_utc: bool = True,
    enqueue: bool = True,
):
    global _logger_manager, _logger
    default_logger.info("Initializing logger...")
    _logger_manager = LoggerManager(
        level=level,
        base_log_dir=base_log_dir or BASE_DIR / "logs",
        rotation=rotation,
        retention=retention,
        use_utc=use_utc,
        enqueue=enqueue,
    )
    _logger = _logger_manager.setup()
    default_logger.info("Logger initialized.")


class _LoggerProxy:
    """代理对象，动态转发调用到真实 logger"""

    def __getattr__(self, name):
        if _logger is None:
            raise RuntimeError("Logger not initialized. Call init_logger() first.")
        return getattr(_logger, name)


class _LoggerManagerProxy:
    """代理对象，动态转发调用到真实 logger_manager"""

    def __getattr__(self, name):
        if _logger_manager is None:
            raise RuntimeError("LoggerManager not initialized. Call init_logger() first.")
        return getattr(_logger_manager, name)


logger = _LoggerProxy()
logger_manager = _LoggerManagerProxy()
