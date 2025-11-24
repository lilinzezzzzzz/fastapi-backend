from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from redis.asyncio import ConnectionPool, Redis
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from internal.config.setting import setting
from pkg import orjson_dumps, orjson_loads
from pkg.logger_tool import logger

# 创建异步引擎
engine = create_async_engine(
    url=setting.sqlalchemy_database_uri,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    json_serializer=orjson_dumps,
    json_deserializer=orjson_loads
)

# 创建异步 session_maker
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session(autoflush: bool = True) -> AsyncGenerator[AsyncSession, Any]:
    async with AsyncSessionLocal() as session:
        if autoflush:
            try:
                yield session
            except Exception as e:
                if session.is_active:
                    await session.rollback()
                raise e
        else:
            with session.no_autoflush:
                try:
                    yield session
                except Exception as e:
                    if session.is_active:
                        await session.rollback()
                    raise e


def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    try:
        compiled_statement = statement
        if parameters:
            compiled_statement = text(statement % tuple(parameters)).compile(compile_kwargs={"literal_binds": True})
        logger.info(f"Executing SQL: {compiled_statement}")
    except Exception as e:
        logger.error(f"Error while printing SQL: {e}")


# 监听 before_cursor_execute 事件，将事件处理函数绑定到 Engine 上
event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)

# 创建全局的连接池实例
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
        logger.error(f"Redis operation failed: {e}")
        raise
