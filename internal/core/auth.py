from internal.cache.redis import cache_dao
from internal.core.exception import AppException, errors


async def verify_token(token: str) -> dict:
    """验证 token，成功返回 user_metadata，失败抛出 AppException"""
    user_metadata: dict | None = await cache_dao.get_auth_user_metadata(token)
    if user_metadata is None:
        raise AppException(errors.Unauthorized, message="Token verification failed: token not found")

    user_id = user_metadata.get("id")
    if not user_id:
        raise AppException(errors.Unauthorized, message="Token verification failed: user_id is None")

    # 检查有没有在token 列表里
    token_list: list = await cache_dao.get_auth_user_token_list(user_id)
    if token not in token_list:
        raise AppException(
            errors.Unauthorized,
            message=f"Token verification failed: token not found in token list, user_id: {user_id}",
        )

    return user_metadata
