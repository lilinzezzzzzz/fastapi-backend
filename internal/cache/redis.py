from internal.infra.redis import cache
from pkg.logger import logger
from pkg.toolkit.json import orjson_loads


class CacheDao:
    """
    Redis 数据访问对象
    """

    @staticmethod
    def make_auth_token_key(token: str) -> str:
        return f"token:{token}"

    @staticmethod
    def make_auth_user_token_list_key(user_id: int) -> str:
        return f"token_list:{user_id}"

    async def get_auth_user_metadata(self, token: str) -> dict | None:
        val = await cache.get_value(self.make_auth_token_key(token))
        if val is None:
            logger.warning("Token verification failed: token not found")
            return None

        return orjson_loads(val)

    async def get_auth_user_token_list(self, user_id: int) -> list[str]:
        val = await cache.get_list(self.make_auth_user_token_list_key(user_id))
        if not val:
            logger.warning(f"Token verification failed: token list not found, user_id: {user_id}")
            return []

        return val

    async def remove_from_list(self, key: str, value: str) -> int:
        """从列表中移除元素"""
        return await cache.remove_from_list(key, value)


cache_dao = CacheDao()
