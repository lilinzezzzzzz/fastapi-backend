# 创建全局的连接池实例
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from redis.asyncio import ConnectionPool, Redis

from internal.config.setting import setting

RedisConnectPool = ConnectionPool.from_url(
    setting.redis_url,
    encoding="utf-8",
    decode_responses=True,
    max_connections=20
)

_redis = Redis(connection_pool=RedisConnectPool)


@asynccontextmanager
async def get_redis() -> AsyncGenerator[Redis, None]:
    try:
        yield _redis
    except Exception as e:
        raise Exception(f"Redis operation failed, err={e}")
