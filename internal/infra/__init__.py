"""基础设施层：数据库、缓存等外部资源连接管理"""

from internal.infra import database, redis

__all__ = ["database", "redis"]
