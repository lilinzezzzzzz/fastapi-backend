from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

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
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=True)


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
