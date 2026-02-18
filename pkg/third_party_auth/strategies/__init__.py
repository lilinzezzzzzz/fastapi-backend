"""第三方认证策略实现模块"""

from .wechat import WeChatAuthStrategy, WeChatConfig

__all__ = [
    "WeChatAuthStrategy",
    "WeChatConfig",
]
