from datetime import UTC, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from internal import BASE_DIR
from pkg.async_logger import LoggerManager, RetentionType, RotationType, logger as default_logger
from pkg.toolkit.types import LazyProxy

if TYPE_CHECKING:
    from loguru import Logger

# 内部持有真实对象
_logger_manager: "LoggerManager | None" = None
_logger: "Logger | None" = None


# --- Getter 函数 ---
def _get_logger() -> "Logger":
    if _logger is None:
        raise RuntimeError("Logger not initialized. Call init_logger() first.")
    return _logger


def _get_logger_manager() -> "LoggerManager":
    if _logger_manager is None:
        raise RuntimeError("LoggerManager not initialized. Call init_logger() first.")
    return _logger_manager


# --- 初始化函数 ---
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


# --- 导出代理对象 ---
logger = LazyProxy(_get_logger)
logger_manager = LazyProxy(_get_logger_manager)
