"""认证服务层"""

from internal.cache.auth import AuthCache, new_auth_cache
from internal.core import AppException, errors


class AuthService:
    def __init__(self, auth_cache: AuthCache):
        self._auth_cache = auth_cache

    async def verify_token(self, token: str) -> dict:
        """验证 token，成功返回 user_metadata，失败抛出 AppException"""
        user_metadata: dict | None = await self._auth_cache.get_user_metadata(token)
        if user_metadata is None:
            raise AppException(errors.Unauthorized, message="Token verification failed: token not found")

        user_id = user_metadata.get("id")
        if not user_id:
            raise AppException(errors.Unauthorized, message="Token verification failed: user_id is None")

        # 检查有没有在token 列表里
        token_list: list = await self._auth_cache.get_user_token_list(user_id)
        if token not in token_list:
            raise AppException(
                errors.Unauthorized,
                message=f"Token verification failed: token not found in token list, user_id: {user_id}",
            )

        return user_metadata


# 全局单例（懒加载）
_auth_service: AuthService | None = None


def new_auth_service() -> AuthService:
    """依赖注入：获取 AuthService 单例"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService(auth_cache=new_auth_cache())
    return _auth_service
