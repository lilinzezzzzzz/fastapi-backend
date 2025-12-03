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
    """
    通用 SQL 日志记录函数，支持 MySQL 和 PostgreSQL (asyncpg)
    """
    try:
        # 1. 优先尝试使用 SQLAlchemy 的 Compiler 生成带参数的 SQL
        # 这种方式最准确，它能处理不同数据库的方言差异
        if context and context.compiled:
            # 使用 literal_binds=True 将参数直接渲染进 SQL 字符串中
            # 注意：这只是用于日志展示，实际执行时依然是参数化的，没有注入风险
            compiled_statement = context.compiled.statement.compile(
                dialect=context.dialect,
                compile_kwargs={"literal_binds": True}
            )
            logger.info(f"Executing SQL: {compiled_statement}")

        # 2. 如果是原生 SQL (text) 或者没有 compiled 上下文，回退到普通打印
        else:
            if parameters:
                # 对于 PostgreSQL (asyncpg)，statement 是 "SELECT ... WHERE id = $1"
                # parameters 是 (1, )
                # 很难手动完美拼接到一起，所以建议将 SQL 和 参数分开打印
                logger.info(f"Executing SQL: {statement} | Params: {parameters}")
            else:
                logger.info(f"Executing SQL: {statement}")

    except Exception as e:
        # 防止日志打印出错导致业务逻辑中断
        logger.error(f"Error while printing SQL: {e}")
        # 兜底：至少打印原始语句
        logger.info(f"Executing SQL (raw): {statement} | Params: {parameters}")


# 监听 before_cursor_execute 事件，将事件处理函数绑定到 Engine 上
event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
