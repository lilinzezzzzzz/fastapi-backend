from collections.abc import Callable
from datetime import UTC, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from internal import BASE_DIR
from pkg.async_logger import LoggerManager, RetentionType, RotationType, logger as default_logger

if TYPE_CHECKING:
    from loguru import Logger

# 内部持有真实对象
_logger_manager: "LoggerManager | None" = None
_logger: "Logger | None" = None


# --- 1. 定义一个通用的懒加载代理类 ---
class LazyProxy:
    """
    一个轻量级的通用代理，只有在访问属性时才去获取真实对象。
    """

    def __init__(self, getter: Callable[[], Any]):
        self._getter = getter

    def __getattr__(self, name: str) -> Any:
        # 每次访问属性（如 logger.info）时，都会执行 getter 获取最新实例
        target = self._getter()
        return getattr(target, name)

    # 这里的 __repr__ 是为了调试方便，显示当前代理状态
    def __repr__(self):
        try:
            target = self._getter()
            return repr(target)
        except RuntimeError:
            return "<Uninitialized LazyProxy>"


# --- 2. 定义获取实例的 Helper 函数 ---
def _get_logger() -> "Logger":
    if _logger is None:
        raise RuntimeError("Logger not initialized. Call init_logger() first.")
    return _logger


def _get_manager() -> "LoggerManager":
    if _logger_manager is None:
        raise RuntimeError("LoggerManager not initialized. Call init_logger() first.")
    return _logger_manager


# --- 3. 初始化逻辑 (保持不变) ---
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
        target = _logger
        return getattr(target, name)


class _LoggerManagerProxy:
    """代理对象，动态转发调用到真实 logger_manager"""

    def __getattr__(self, name):
        if _logger_manager is None:
            raise RuntimeError("LoggerManager not initialized. Call init_logger() first.")
        target = _logger_manager
        return getattr(target, name)


# 在运行时，logger 是 LazyProxy 实例
logger = _LoggerProxy()
logger_manager = _LoggerManagerProxy()
