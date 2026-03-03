"""核心模块：异常定义、错误码等通用能力"""

from internal.core.errors import GlobalErrors, errors
from internal.core.exception import AppException

__all__ = [
    "AppException",
    "GlobalErrors",
    "errors",
]
