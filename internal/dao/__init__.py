"""数据访问层 (Data Access Object)"""

from internal.dao.cache import CacheDao, cache_dao

__all__ = [
    "CacheDao",
    "cache_dao",
]
