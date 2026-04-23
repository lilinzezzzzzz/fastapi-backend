"""数据访问层 (Data Access Object)"""

from internal.dao.cache import CacheDao, new_cache_dao

__all__ = [
    "CacheDao",
    "new_cache_dao",
]
