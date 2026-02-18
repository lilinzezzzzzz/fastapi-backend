"""第三方认证配置数据类 - 类型安全的配置容器"""

from dataclasses import dataclass


@dataclass
class WeChatConfig:
    """微信开放平台配置

    Attributes:
        app_id: 微信公众号/小程序 AppID
        app_secret: 微信公众号/小程序 AppSecret
        grant_type: 授权类型，默认 'authorization_code'
    """

    app_id: str
    app_secret: str
    grant_type: str = "authorization_code"

    def __post_init__(self) -> None:
        """验证配置有效性"""
        if not self.app_id or not self.app_secret:
            raise ValueError("WeChat config requires app_id and app_secret")


@dataclass
class AlipayConfig:
    """支付宝开放平台配置（预留）

    Attributes:
        app_id: 支付宝应用 AppID
        app_private_key: 应用私钥（用于签名）
        alipay_public_key: 支付宝公钥（用于验签）
        encrypt_key: _AES_加密密钥（可选）
    """

    app_id: str
    app_private_key: str
    alipay_public_key: str
    encrypt_key: str | None = None

    def __post_init__(self) -> None:
        """验证配置有效性"""
        if not self.app_id or not self.app_private_key or not self.alipay_public_key:
            raise ValueError(
                "Alipay config requires app_id, app_private_key, and alipay_public_key"
            )
