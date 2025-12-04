from internal.infra.redis import cache_client
from pkg import token_list_cache_key
from pkg.logger_tool import logger


async def verify_token(token: str) -> tuple[dict | None, bool]:
    user_data: dict = await cache_client.get_token_value(token)
    if user_data is None:
        logger.warning("Token verification failed: token not found")
        return None, False

    user_id = user_data.get("id")
    # 检查有没有在token 列表里
    token_list = await cache_client.get_list(token_list_cache_key(user_id))
    if token_list is None or token not in token_list:
        logger.warning(f"Token verification failed: token not found in token list, user_id: {user_id}")
        return None, False

    return user_data, True
