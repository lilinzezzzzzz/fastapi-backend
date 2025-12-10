def token_cache_key(token: str) -> str:
    return f"token:{token}"


def token_list_cache_key(user_id: int) -> str:
    return f"token_list:{user_id}"
