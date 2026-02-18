"""第三方认证策略工厂 - 可复用的策略注册表"""

from enum import Enum

from pkg.logger import logger

from .base import BaseThirdPartyAuthStrategy
from .strategies.wechat import WeChatAuthStrategy


class ThirdPartyPlatform(str, Enum):
    """第三方平台枚举

    添加新平台时在此处声明：
        GOOGLE = "google"
        GITHUB = "github"
    """

    WECHAT = "wechat"
    ALIPAY = "alipay"


class ThirdPartyAuthFactory:
    """第三方认证策略工厂

    使用工厂模式创建策略实例，支持动态注册新的认证策略。

    使用示例:
        ```python
        # 获取已注册的策略
        strategy = ThirdPartyAuthFactory.get_strategy(ThirdPartyPlatform.WECHAT)

        # 注册新的策略（在模块初始化时调用）
        from .google import GoogleAuthStrategy
        ThirdPartyAuthFactory.register_strategy(
            ThirdPartyPlatform.GOOGLE,
            GoogleAuthStrategy
        )
        ```
    """

    # 策略注册表
    _strategies: dict[ThirdPartyPlatform, type[BaseThirdPartyAuthStrategy]] = {
        ThirdPartyPlatform.WECHAT: WeChatAuthStrategy,
        # 可以在这里注册其他策略，例如：
        # ThirdPartyPlatform.ALIPAY: AlipayAuthStrategy,
        # ThirdPartyPlatform.GOOGLE: GoogleAuthStrategy,
    }

    @classmethod
    def register_strategy(
        cls,
        platform: ThirdPartyPlatform,
        strategy_class: type[BaseThirdPartyAuthStrategy]
    ) -> None:
        """
        注册新的认证策略

        Args:
            platform: 平台标识
            strategy_class: 策略类

        Example:
            ```python
            from pkg.third_party_auth.strategies.alipay import AlipayAuthStrategy

            ThirdPartyAuthFactory.register_strategy(
                ThirdPartyPlatform.ALIPAY,
                AlipayAuthStrategy
            )
            ```
        """
        cls._strategies[platform] = strategy_class
        logger.info(f"Registered third-party auth strategy for {platform.value}")

    @classmethod
    def get_strategy(cls, platform: ThirdPartyPlatform | str) -> BaseThirdPartyAuthStrategy:
        """
        获取对应平台的认证策略实例

        Args:
            platform: 平台标识（字符串或枚举值）

        Returns:
            BaseThirdPartyAuthStrategy: 策略实例

        Raises:
            ValueError: 当平台未注册时
        """
        # 支持字符串输入
        if isinstance(platform, str):
            try:
                platform = ThirdPartyPlatform(platform.lower())
            except ValueError as e:
                raise ValueError(f"Unsupported third-party platform: {platform}") from e

        # 从注册表获取策略类
        strategy_class = cls._strategies.get(platform)
        if not strategy_class:
            raise ValueError(
                f"Third-party platform '{platform.value}' not supported. "
                f"Available platforms: {[p.value for p in ThirdPartyPlatform]}"
            )

        # 创建并返回策略实例
        return strategy_class()

    @classmethod
    def get_available_platforms(cls) -> list[str]:
        """
        获取所有可用的平台列表

        Returns:
            平台名称列表
        """
        return [platform.value for platform in cls._strategies.keys()]
