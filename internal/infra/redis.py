from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from redis.asyncio import ConnectionPool, Redis

from internal.config.load_config import settings
from pkg.logger import logger
from pkg.toolkit.cache import CacheClient
from pkg.toolkit.types import LazyProxy

# 1. 定义全局变量，初始为 None
_redis_pool: ConnectionPool | None = None
_redis_client: Redis | None = None
# cache_client 也改为全局变量，在 init 中初始化
_cache: CacheClient | None = None


def init_async_redis() -> None:
    """
    初始化 Redis 连接池。
    应在 FastAPI lifespan 或 Celery worker_process_init 中调用。
    """
    global _redis_pool, _redis_client, _cache

    logger.info("Initializing Redis connection...")

    if _redis_pool is None:
        # 创建连接池
        _redis_pool = ConnectionPool.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=getattr(settings, "REDIS_MAX_CONNECTIONS", 20),
        )

    if _cache is None:
        # 创建客户端实例
        _redis_client = Redis(connection_pool=_redis_pool)

    # 初始化缓存客户端封装 (假设 new_cache_client 接受 session_provider)
    # 注意：我们传入 get_redis 函数本身，它是一个稳定的引用
    if _cache is None:
        _cache = CacheClient(session_provider=get_redis)

    logger.success("Redis initialized successfully.")


async def close_async_redis() -> None:
    """关闭 Redis 连接"""
    global _redis_client, _redis_pool, _cache

    if _redis_client:
        await _redis_client.close()  # 异步关闭客户端
        logger.warning("Redis connection closed.")

    # 清理引用
    _redis_client = None
    _redis_pool = None
    _cache = None


def reset_async_redis() -> None:
    global _redis_client, _redis_pool, _cache

    _redis_client = None
    _redis_pool = None
    _cache = None


@asynccontextmanager
async def get_redis() -> AsyncGenerator[Redis, None]:
    """
    Redis Session 获取上下文管理器
    """
    if _redis_client is None:
        raise RuntimeError("Redis is not initialized. Call init_redis() first.")

    try:
        yield _redis_client
    except Exception as e:
        # 这里通常不需要做太多回滚操作，Redis 操作多为原子的或即时的
        # 但可以记录日志
        logger.error(f"Redis operation failed: {e}")
        raise e


def _get_cache() -> CacheClient:
    """
    获取全局缓存客户端实例的 Helper 函数
    替代直接 import cache_client 变量，防止 import 时为 None 的问题
    """
    if _cache is None:
        raise RuntimeError("Redis/Cache is not initialized. Call init_redis() first.")
    return _cache


cache = LazyProxy[CacheClient](_get_cache)
