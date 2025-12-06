import asyncio
import functools
import time
import uuid
from contextlib import AbstractAsyncContextManager
from typing import Any, Callable, Optional, List

from loguru import logger
from orjson import JSONDecodeError
from redis.asyncio import Redis

from pkg import create_uuid_token, orjson_dumps, orjson_loads, token_cache_key, token_list_cache_key

SessionProvider = Callable[[], AbstractAsyncContextManager[Redis]]


def handle_redis_exception(func):
    """
    装饰器：统一处理 Redis 操作的异常捕获和日志记录
    """

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            # 获取函数名用于日志
            func_name = func.__name__
            raise Exception(f"Redis error in '{func_name}': {repr(e)} | args: {args}")

    return wrapper


class CacheClient:
    def __init__(self, session_provider: SessionProvider):
        self.session_provider = session_provider

    async def _get_conn(self):
        """辅助方法：获取连接上下文"""
        return self.session_provider()

    @handle_redis_exception
    async def set_token(self, token: str, user_data: dict, ex: int = 10800):
        key = token_cache_key(token)
        value = orjson_dumps(user_data)
        await self.set_value(key, value, ex)

    @handle_redis_exception
    async def get_token_value(self, token: str) -> dict:
        return await self.get_value(token_cache_key(token))

    @handle_redis_exception
    async def set_token_list(self, user_id: int, token: str):
        """
        原子性地将 Token 加入列表，并保持列表长度不超过 3。
        如果溢出，弹出最早的 Token。
        """
        cache_key = token_list_cache_key(user_id)
        # Lua 脚本逻辑：RPUSH 新值 -> 检查 LLEN -> 如果 > 3 则 LPOP
        # 这保证了操作的原子性，避免并发导致的列表膨胀
        script = """
        redis.call('RPUSH', KEYS[1], ARGV[1])
        if redis.call('LLEN', KEYS[1]) > 3 then
            return redis.call('LPOP', KEYS[1])
        end
        return nil
        """

        async with self.session_provider() as redis:
            popped_value = await redis.eval(script, 1, cache_key, token)

            if popped_value:
                # 统一转为 string 记录日志
                old_token = popped_value.decode() if isinstance(popped_value, bytes) else popped_value
                logger.warning(
                    f"Token list for user {user_id} is full. Popped old token: {old_token}"
                )

    @handle_redis_exception
    async def set_value(self, key: str, value: Any, ex: int | None = None) -> bool:
        async with self.session_provider() as redis:
            return await redis.set(key, value, ex=ex)

    @handle_redis_exception
    async def get_value(self, key: str) -> Any:
        async with self.session_provider() as redis:
            value = await redis.get(key)
            if value is None:
                return None

            if isinstance(value, bytes):
                value = value.decode("utf-8")

            try:
                return orjson_loads(value)
            except JSONDecodeError:
                # 如果不是 JSON，直接返回字符串
                return value

    @handle_redis_exception
    async def delete_key(self, key: str) -> int:
        async with self.session_provider() as redis:
            return await redis.delete(key)

    @handle_redis_exception
    async def set_expiry(self, key: str, ex: int) -> bool:
        async with self.session_provider() as redis:
            return await redis.expire(key, ex)

    @handle_redis_exception
    async def key_exists(self, key: str) -> bool:
        async with self.session_provider() as redis:
            return await redis.exists(key) > 0

    @handle_redis_exception
    async def get_ttl(self, key: str) -> int:
        async with self.session_provider() as redis:
            return await redis.ttl(key)

    @handle_redis_exception
    async def set_hash(self, name: str, key: str, value: Any) -> bool:
        async with self.session_provider() as redis:
            return await redis.hset(name, key, value) > 0

    @handle_redis_exception
    async def get_hash(self, name: str, key: str) -> Optional[str]:
        async with self.session_provider() as redis:
            value = await redis.hget(name, key)
            return value.decode() if value else None

    @handle_redis_exception
    async def push_to_list(self, name: str, value: Any, direction: str = "right") -> int:
        async with self.session_provider() as redis:
            if direction == "left":
                return await redis.lpush(name, value)
            return await redis.rpush(name, value)

    @handle_redis_exception
    async def get_list(self, name: str) -> List[str]:
        """
        获取列表所有值，并强制转换为字符串列表。
        """
        async with self.session_provider() as redis:
            values = await redis.lrange(name, 0, -1)
            if not values:
                return []
            # 统一解码处理
            return [v.decode() if isinstance(v, bytes) else v for v in values]

    @handle_redis_exception
    async def left_pop_list(self, name: str) -> Optional[str]:
        async with self.session_provider() as redis:
            value = await redis.lpop(name)
            return value.decode() if value else None

    async def login_and_set_token(self, user_data: dict) -> str:
        # 该方法是业务组合逻辑，本身不需要加 Redis 装饰器，因为它调用的内部方法已经处理了异常
        # 但为了捕获内部逻辑错误，也可以加上 try-except，或者依赖上层调用处理
        token = create_uuid_token()
        user_id = user_data["id"]

        # 并行执行写入 Token 和更新列表，减少等待时间（可选优化，视业务严格程度而定）
        # 这里使用 gather 并发执行，因为两者互不强依赖（除了用户ID）
        await asyncio.gather(
            self.set_token(token, user_data),
            self.set_token_list(user_id, token)
        )
        return token

    async def release_lock(self, lock_key: str, identifier: str) -> bool:
        unlock_script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        else
            return 0
        end
        """
        try:
            async with self.session_provider() as redis:
                result = await redis.eval(unlock_script, 1, lock_key, identifier)
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to release lock {lock_key}: {repr(e)}")
            return False

    async def acquire_lock(
            self,
            lock_key: str,
            expire_ms: int = 10000,
            timeout_ms: int = 5000,
            retry_interval_ms: int = 100
    ) -> Optional[str]:

        lock_script = """
        if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2]) then
            return 1
        else
            return 0
        end
        """
        identifier = uuid.uuid4().hex
        start_time = time.perf_counter()

        # 优化：在循环外处理异常捕获，避免过于复杂的 try-catch 嵌套
        try:
            while (time.perf_counter() - start_time) * 1000 < timeout_ms:
                async with self.session_provider() as redis:
                    acquired = await redis.eval(
                        lock_script, 1, lock_key, identifier, str(expire_ms)
                    )

                if acquired:
                    return identifier

                # 使用 await asyncio.sleep 非阻塞等待
                await asyncio.sleep(retry_interval_ms / 1000)
        except Exception as e:
            logger.error(f"Error acquiring lock {lock_key}: {repr(e)}")
            # 获取锁失败（报错）时返回 None
            return None

        return None
