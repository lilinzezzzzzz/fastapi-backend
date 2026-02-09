"""
pkg.logger - 统一的日志管理包

使用方式：
使用 init_logger() + logger 代理对象（延迟初始化）

使用示例:
    from pkg.logger import init_logger, logger

    # 在应用启动时初始化
    init_logger(level="DEBUG", base_log_dir=Path("/var/log/myapp"))

    # 之后在任何地方使用
    logger.info("Application started")
"""
from datetime import UTC, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from pkg.logger.handler import LogFormat, LoggerHandler, RetentionType, RotationType
from pkg.toolkit.types import LazyProxy

if TYPE_CHECKING:
    from loguru import Logger

# 内部持有真实对象（延迟初始化）
_logger_manager: "LoggerHandler | None" = None
_logger: "Logger | None" = None


# --- Getter 函数 ---
def _get_logger() -> "Logger":
    if _logger is None:
        raise RuntimeError("Logger not initialized. Call init_logger() first.")
    return _logger


def _get_logger_manager() -> "LoggerHandler":
    if _logger_manager is None:
        raise RuntimeError("LoggerHandler not initialized. Call init_logger() first.")
    return _logger_manager


# --- 初始化函数 ---
def init_logger(
    *,
    level: str = "INFO",
    base_log_dir: Path | None = None,
    system_subdir: str | None = None,
    rotation: RotationType = time(0, 0, 0, tzinfo=UTC),
    retention: RetentionType = timedelta(days=30),
    compression: str | None = None,
    use_utc: bool = True,
    enqueue: bool = True,
    log_format: LogFormat | str = LogFormat.TEXT,
    write_to_file: bool = True,
    write_to_console: bool = True,
    enable_otel_bridge: bool = True,
) -> "Logger":
    """
    初始化应用层 Logger。

    :param level: 日志等级 (e.g., "INFO", "DEBUG")
    :param base_log_dir: 日志存放的根目录
    :param system_subdir: 系统日志子目录名，传 None 则直接存在 base_log_dir 下
    :param rotation: 轮转策略 (默认: 每天 00:00, UTC时间)
    :param retention: 保留策略 (默认: 30天)
    :param compression: 压缩格式 (e.g., "zip")
    :param use_utc: 是否强制使用 UTC 时间
    :param enqueue: 是否使用多进程安全的队列写入
    :param log_format: 日志格式 (LogFormat.JSON 或 LogFormat.TEXT，默认 LogFormat.TEXT)
    :param write_to_file: 是否写入文件
    :param write_to_console: 是否输出到控制台
    :param enable_otel_bridge: 是否启用 OTel 日志桥接（将日志转发到 Logs Backend）
    :return: 初始化后的 Logger 实例
    """
    global _logger_manager, _logger

    _logger_manager = LoggerHandler(
        level=level,
        base_log_dir=base_log_dir,
        system_subdir=system_subdir,
        rotation=rotation,
        retention=retention,
        compression=compression,
        use_utc=use_utc,
        enqueue=enqueue,
        log_format=log_format,
    )
    _logger = _logger_manager.setup(
        write_to_file=write_to_file,
        write_to_console=write_to_console,
        enable_otel_bridge=enable_otel_bridge,
    )

    return _logger


def get_logger_manager() -> "LoggerHandler":
    """获取当前的 LoggerHandler 实例（需先调用 init_logger）"""
    return _get_logger_manager()


# --- 导出代理对象 ---
logger: "Logger" = LazyProxy["Logger"](_get_logger)  # type: ignore[assignment]

# --- 公开 API ---
__all__ = [
    # 类
    "LoggerHandler",
    # 枚举
    "LogFormat",
    # 类型别名
    "RotationType",
    "RetentionType",
    # 初始化函数
    "init_logger",
    "get_logger_manager",
    # Logger 实例
    "logger",
]
