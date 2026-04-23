"""认证服务层"""

from internal.core import AppException, errors
from internal.dao.cache import CacheDao, new_cache_dao


class AuthService:
    def __init__(self, cache_dao: CacheDao):
        self._cache_dao = cache_dao

    async def verify_token(self, token: str) -> dict:
        """验证 token，成功返回 user_metadata，失败抛出 AppException"""
        user_metadata: dict | None = await self._cache_dao.get_auth_user_metadata(token)
        if user_metadata is None:
            raise AppException(errors.Unauthorized, message="Token verification failed: token not found")

        user_id = user_metadata.get("id")
        if not user_id:
            raise AppException(errors.Unauthorized, message="Token verification failed: user_id is None")

        # 检查有没有在token 列表里
        token_list: list = await self._cache_dao.get_auth_user_token_list(user_id)
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
        _auth_service = AuthService(cache_dao=new_cache_dao())
    return _auth_service
