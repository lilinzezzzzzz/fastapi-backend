"""Redis 基础设施模块"""

from internal.infra.redis.connection import (
    close_async_redis,
    get_redis,
    init_async_redis,
    redis_client,
    reset_async_redis,
)
from internal.infra.redis.dao import CacheDao, cache_dao

__all__ = [
    # 连接管理
    "redis_client",
    "init_async_redis",
    "close_async_redis",
    "reset_async_redis",
    "get_redis",
    # 数据访问
    "CacheDao",
    "cache_dao",
]
