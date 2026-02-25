"""第三方认证策略抽象基类 - 无业务依赖的通用接口"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ThirdPartyUserInfo:
    """第三方用户信息统一结构

    Attributes:
        open_id: 第三方平台唯一标识
        union_id: 跨应用统一标识（可选，如微信 UnionID）
        avatar: 头像 URL
        nickname: 昵称
        raw_data: 原始数据（保留扩展性）
    """

    open_id: str
    union_id: str | None = None
    avatar: str | None = None
    nickname: str | None = None
    raw_data: dict[str, Any] | None = None


class BaseThirdPartyAuthStrategy(ABC):
    """第三方认证策略抽象基类

    所有第三方登录策略都必须实现此接口。
    策略应该是无状态的，配置通过构造函数注入。
    """

    @abstractmethod
    async def get_access_token(self, code: str) -> dict[str, Any]:
        """
        通过授权码获取 access_token

        Args:
            code: 授权码（微信 code、支付宝 auth_code 等）

        Returns:
            包含 access_token、expires_in 等信息的字典

        Raises:
            ValueError: 当 API 返回错误时
        """
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str, open_id: str) -> ThirdPartyUserInfo:
        """
        获取第三方用户信息

        Args:
            access_token: 访问令牌
            open_id: 用户唯一标识

        Returns:
            ThirdPartyUserInfo: 标准化的用户信息

        Raises:
            ValueError: 当 API 返回错误时
        """
        pass

    @abstractmethod
    def get_platform_name(self) -> str:
        """
        获取平台名称

        Returns:
            平台名称，如 'wechat', 'alipay' 等
        """
        pass

    async def close(self) -> None:
        """
        关闭资源（HTTP 客户端等）

        子类可以重写此方法进行资源清理。
        默认实现为空。
        """
        pass
