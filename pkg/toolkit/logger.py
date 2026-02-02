"""pkg.toolkit.logger - 兼容性重导出模块

此模块已迁移至 pkg.logger，保留此文件仅为了向后兼容。
请更新你的导入语句为:
    from pkg.logger import LoggerManager, logger, ...

此兼容模块将在后续版本中移除。
"""
import warnings

from pkg.logger import (
    LoggerManager,
    RetentionType,
    RotationType,
    init_logger,
    logger,
)

warnings.warn(
    "pkg.toolkit.logger 已废弃，请使用 pkg.logger 代替",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "LoggerManager",
    "RotationType",
    "RetentionType",
    "init_logger",
    "logger",
]
