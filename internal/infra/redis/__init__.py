"""Redis 基础设施模块

注意: CacheDao 和 cache_dao 已移动到 internal/dao/cache.py
此处重新导出是为了向后兼容，新代码请使用: from internal.dao import cache_dao
"""

# 向后兼容：从 dao 层重新导出
from internal.dao.cache import CacheDao, cache_dao  # noqa: PLC0414
from internal.infra.redis.connection import (
    close_async_redis,
    get_redis,
    init_async_redis,
    redis_client,
    reset_async_redis,
)

__all__ = [
    # 连接管理
    "redis_client",
    "init_async_redis",
    "close_async_redis",
    "reset_async_redis",
    "get_redis",
    # 数据访问 (向后兼容，建议从 internal.dao 导入)
    "CacheDao",
    "cache_dao",
]
