"""基础设施层：数据库、缓存、向量存储等外部资源连接管理"""

from internal.infra import redis, vector

__all__ = ["redis", "vector"]
