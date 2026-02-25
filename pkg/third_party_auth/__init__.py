"""第三方认证模块 - 可复用的策略模式实现

使用策略模式 + 工厂模式设计，支持方便扩展多种第三方登录方式：
- 微信登录
- 支付宝登录
- Google 登录
- GitHub 登录
- 等等...

架构设计:
    - base: 抽象基类和数据类（无业务依赖）
    - strategies: 具体平台策略实现（配置通过参数注入）
    - factory: 策略工厂和平台枚举

使用示例:
    ```python
    from pkg.third_party_auth import WeChatAuthStrategy, WeChatConfig

    # 通过配置创建策略实例
    strategy = WeChatAuthStrategy(
        config=WeChatConfig(
            app_id="your_app_id",
            app_secret="your_app_secret",
        )
    )

    # 使用策略
    token_info = await strategy.get_access_token(code)
    user_info = await strategy.get_user_info(
        access_token=token_info["access_token"],
        open_id=token_info["openid"]
    )
    ```
"""

from .base import BaseThirdPartyAuthStrategy, ThirdPartyUserInfo
from .factory import ThirdPartyAuthFactory, ThirdPartyPlatform
from .strategies.wechat import WeChatAuthStrategy, WeChatConfig

__all__ = [
    # 基础接口
    "BaseThirdPartyAuthStrategy",
    "ThirdPartyUserInfo",

    # 工厂和枚举
    "ThirdPartyPlatform",
    "ThirdPartyAuthFactory",

    # 具体策略和配置
    "WeChatAuthStrategy",
    "WeChatConfig",
]
