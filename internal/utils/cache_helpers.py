import asyncio
import time
import uuid
from typing import Any

from fastapi import status
from loguru import logger
from orjson import JSONDecodeError

from internal.infra.default_db_session import get_redis
from internal.core.exception import AppException
from pkg import create_uuid_token, orjson_dumps, orjson_loads, token_cache_key, token_list_cache_key


class Cache:
    @classmethod
    async def set_token(cls, token: str, user_data: dict, ex: int = 10800):
        """
        设置会话键值，并设置过期时间。
        """
        key = token_cache_key(token)
        value = orjson_dumps(user_data)
        await cls.set_value(key, value, ex)

    @classmethod
    async def get_token_value(cls, token: str) -> dict:
        """
        获取会话中的用户ID和用户类型。
        """
        return await cls.get_value(token_cache_key(token))

    @classmethod
    async def set_token_list(cls, user_id: int, token: str):
        cache_key = token_list_cache_key(user_id)
        token_list = await cls.get_list(cache_key)
        length_token_list = len(token_list)
        try:
            async with get_redis() as redis:
                if not token_list or length_token_list < 3:
                    await redis.rpush(cache_key, token)
                else:
                    if len(token_list) >= 3:
                        old_token = await redis.lpop(cache_key)
                        # 插入新的token
                        await redis.rpush(cache_key, token)
                        logger.warning(
                            f"token list for user {user_id} is full, popping and deleting oldest token: {old_token}")
        except Exception as e:
            logger.error(f"Failed to pop ande delete value from list {cache_key}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 设置键值对
    @classmethod
    async def set_value(cls, key: str, value: Any, ex: int | None = None) -> bool:
        """
        设置键值对并可选设置过期时间。
        """
        try:
            async with get_redis() as redis:
                return await redis.set(key, value, ex=ex)
        except Exception as e:
            logger.error(f"Failed to set key {key}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 获取键值
    @classmethod
    async def get_value(cls, key: str) -> dict | Any:
        """
        获取键值。
        """
        try:
            async with get_redis() as redis:
                value = await redis.get(key)
                if value is None:
                    return None

                if isinstance(value, bytes):
                    value = value.decode("utf-8")

                try:
                    return orjson_loads(value)
                except JSONDecodeError as _:
                    return value
        except Exception as e:
            logger.error(f"Failed to get key {key}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 删除键
    @classmethod
    async def delete_key(cls, key: str) -> int:
        """
        删除键。
        """
        try:
            async with get_redis() as redis:
                return await redis.delete(key)
        except Exception as e:
            logger.error(f"failed to delete key {key}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 设置过期时间
    @classmethod
    async def set_expiry(cls, key: str, ex: int) -> bool:
        """
        设置键的过期时间。
        """
        try:
            async with get_redis() as redis:
                return await redis.expire(key, ex)
        except Exception as e:
            logger.error(f"Failed to set expiry for key {key}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 检查键是否存在
    @classmethod
    async def key_exists(cls, key: str) -> bool:
        """
        检查键是否存在。
        """
        try:
            async with get_redis() as redis:
                return await redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check existence of key {key}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 获取键的剩余 TTL
    @classmethod
    async def get_ttl(cls, key: str) -> int:
        """
        获取键的剩余生存时间。
        """
        try:
            async with get_redis() as redis:
                return await redis.ttl(key)
        except Exception as e:
            logger.error(f"Failed to get TTL for key {key}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 添加到哈希表
    @classmethod
    async def set_hash(cls, name: str, key: str, value: Any) -> bool:
        """
        在 Redis 哈希表中设置键值。
        """
        try:
            async with get_redis() as redis:
                return await redis.hset(name, key, value) > 0
        except Exception as e:
            logger.error(f"Failed to set hash {name}:{key}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 获取哈希表中的值
    @classmethod
    async def get_hash(cls, name: str, key: str) -> str | None:
        """
        从 Redis 哈希表中获取值。
        """
        try:
            async with get_redis() as redis:
                value = await redis.hget(name, key)
                return value.decode() if value else None
        except Exception as e:
            logger.error(f"Failed to get hash {name}:{key}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 向列表添加值
    @classmethod
    async def push_to_list(cls, name: str, value: Any, direction: str = "right") -> int:
        """
        向列表中添加值。
        """
        try:
            async with get_redis() as redis:
                if direction == "left":
                    return await redis.lpush(name, value)
                else:
                    return await redis.rpush(name, value)
        except Exception as e:
            logger.error(f"Failed to push value to list {name}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # 获取列表中的所有值
    @classmethod
    async def get_list(cls, name: str) -> list[str]:
        """
        获取列表中的所有值。
        """
        try:
            async with get_redis() as redis:
                values = await redis.lrange(name, 0, -1)
                return values
        except Exception as e:
            logger.error(f"Failed to get list {name}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    @classmethod
    async def left_pop_list(cls, name: str) -> str | None:
        """
        从列表左侧弹出一个值。
        """
        try:
            async with get_redis() as redis:
                value = await redis.lpop(name)
                return value.decode() if value else None
        except Exception as e:
            logger.error(f"Failed to pop value from list {name}: {repr(e)}")
            raise AppException(code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    @classmethod
    async def login_and_set_token(cls, user_data: dict) -> str:
        token = create_uuid_token()
        user_id = user_data["id"]

        await cls.set_token(token, user_data)
        await cls.set_token_list(user_id, token)
        return token

    @classmethod
    async def release_lock(cls, lock_key: str, identifier: str) -> bool:
        """
        释放分布式锁
        :param lock_key: 锁的键名
        :param identifier: 锁的唯一标识符
        :return: 是否成功释放
        """
        # 解锁的 Lua 脚本（保持原有）
        unlock_script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        else
            return 0
        end
        """

        async with get_redis() as redis:
            result = await redis.eval(
                unlock_script,
                1,  # 键数量
                lock_key,
                identifier
            )
        return bool(result)

    @classmethod
    async def acquire_lock(
            cls,
            lock_key: str,
            expire_ms: int = 10000,
            timeout_ms: int = 5000,
            retry_interval_ms: int = 100
    ) -> str | None:
        """
        获取分布式锁
        :param lock_key: 锁的键名
        :param expire_ms: 锁的自动过期时间（毫秒）
        :param timeout_ms: 获取锁的总超时时间（毫秒）
        :param retry_interval_ms: 重试间隔（毫秒）
        :return: 锁的唯一标识符（获取失败返回 None）
        """

        # 加锁的 Lua 脚本（保证原子性）
        lock_script = """
        if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2]) then
            return 1
        else
            return 0
        end
        """

        identifier = str(uuid.uuid4().hex)
        start_time = time.perf_counter()

        while (time.perf_counter() - start_time) * 1000 < timeout_ms:
            # 原子性尝试加锁
            async with  get_redis() as redis:
                acquired = await redis.eval(
                    lock_script,
                    1,  # 键数量
                    lock_key,
                    identifier,
                    str(expire_ms)
                )

                if acquired:
                    return identifier

                # 等待重试
                await asyncio.sleep(retry_interval_ms / 1000)

        return None


cache = Cache()