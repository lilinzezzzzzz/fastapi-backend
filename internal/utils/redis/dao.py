from internal.infra.redis import redis_client
from pkg.logger import logger
from pkg.toolkit.json import orjson_dumps, orjson_loads
from pkg.toolkit.redis_client import RedisClient


class CacheDao:
    """
    Redis 数据访问对象
    """

    def __init__(self, redis_cli: RedisClient):
        """
        Args:
            redis_cli: RedisClient 实例，必须传入
        """
        self._redis = redis_cli

    @staticmethod
    def make_auth_token_key(token: str) -> str:
        return f"token:{token}"

    @staticmethod
    def make_auth_user_token_list_key(user_id: int) -> str:
        return f"token_list:{user_id}"

    async def get_auth_user_metadata(self, token: str) -> dict | None:
        val = await self._redis.get_value(self.make_auth_token_key(token))
        if val is None:
            logger.warning("Token verification failed: token not found")
            return None

        return orjson_loads(val)

    async def get_auth_user_token_list(self, user_id: int) -> list[str]:
        val = await self._redis.get_list(self.make_auth_user_token_list_key(user_id))
        if not val:
            logger.warning(f"Token verification failed: token list not found, user_id: {user_id}")
            return []

        return val

    async def set_auth_user_metadata(self, token: str, metadata: dict, ex: int | None = None) -> bool:
        """设置用户元数据"""
        json_str = orjson_dumps(metadata)
        return await self._redis.set_value(self.make_auth_token_key(token), json_str, ex=ex)

    async def remove_from_list(self, key: str, value: str) -> int:
        """从列表中移除元素"""
        return await self._redis.remove_from_list(key, value)

    async def push_to_list(self, key: str, value: str) -> int:
        """向列表添加元素"""
        return await self._redis.push_to_list(key, value)

    async def delete_key(self, key: str) -> int:
        """删除键，返回删除的键数量"""
        return await self._redis.delete_key(key)

    async def set_dict(self, key: str, value: dict, ex: int | None = None) -> bool:
        """设置字典类型的值，自动 JSON 序列化"""
        return await self._redis.set_dict(key, value, ex=ex)


cache_dao = CacheDao(redis_cli=redis_client)
