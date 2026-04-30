"""Redis 基础设施模块

只负责连接生命周期与 client 实例。
业务缓存访问见 `internal/cache/`。
"""

from internal.infra.redis.connection import (
    close_async_redis,
    get_redis,
    init_async_redis,
    redis_client,
    reset_async_redis,
)

__all__ = [
    "redis_client",
    "init_async_redis",
    "close_async_redis",
    "reset_async_redis",
    "get_redis",
]
