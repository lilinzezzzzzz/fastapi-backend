from internal.dao.redis import cache_dao


async def verify_token(token: str) -> tuple[str | dict | None, bool]:
    user_metadata: dict | None = await cache_dao.get_auth_user_metadata(token)
    if user_metadata is None:
        return "Token verification failed: token not found", False

    user_id = user_metadata.get("id")
    if not user_id:
        return "Token verification failed: user_id is None", False

    # 检查有没有在token 列表里
    token_list: list = await cache_dao.get_auth_user_token_list(user_id)
    if token not in token_list:
        return f"Token verification failed: token not found in token list, user_id: {user_id}", False

    return user_metadata, True
