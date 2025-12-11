import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from internal.config.load_config import setting
from pkg.async_database import new_async_engine, new_async_session_maker
from pkg.async_logger import logger
from pkg.toolkit.json import orjson_dumps, orjson_loads

# 全局单例变量，初始为 None
_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


# ---------------------- 1. 生命周期管理 ----------------------

def init_db() -> None:
    """
    初始化数据库连接池。
    应在 FastAPI lifespan 或 Celery worker_process_init 中调用。
    """
    global _engine, _session_maker
    logger.info("Initializing Database Connection...")
    # 幂等性检查：如果已经初始化，直接返回
    if _engine is not None:
        logger.info("Database connection already initialized.")
        return

    # 1. 创建 Engine
    _engine = new_async_engine(
        database_uri=setting.sqlalchemy_database_uri,
        echo=False,  # 通常设为 False，由下方的 event listener 接管日志
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=1800,
        json_serializer=orjson_dumps,
        json_deserializer=orjson_loads
    )

    # 2. 注册 SQL 监控事件 (整合了你原本 default_db_session 中的逻辑)
    _register_event_listeners(_engine)

    # 3. 创建 SessionMaker
    _session_maker = new_async_session_maker(engine=_engine)
    logger.info("Database connection initialized successfully.")


async def close_db() -> None:
    """关闭数据库连接池"""
    global _engine, _session_maker
    if _engine:
        await _engine.dispose()
        logger.info("Database connection disposed.")
    _engine = None
    _session_maker = None


# ---------------------- 2. Session 获取 ----------------------

@asynccontextmanager
async def get_session(autoflush: bool = True) -> AsyncGenerator[AsyncSession, Any]:
    """
    通用的 Session 获取上下文管理器，FastAPI 和 Celery 均可用。
    """
    session_maker = _session_maker

    if session_maker is None:
        raise RuntimeError("Database is not initialized. Call init_db() first.")

    async with session_maker() as session:
        if autoflush:
            try:
                yield session
            except Exception:
                if session.is_active:
                    await session.rollback()
                raise
        else:
            with session.no_autoflush:
                try:
                    yield session
                except Exception:
                    if session.is_active:
                        await session.rollback()
                    raise


# ---------------------- 3. SQL 监控逻辑 (私有) ----------------------

def _register_event_listeners(engine: AsyncEngine):
    """注册 SQLAlchemy 事件监听"""
    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(engine.sync_engine, "after_cursor_execute", _after_cursor_execute)


def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    if context:
        setattr(context, "_query_start_time", time.perf_counter())


def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    if not context or not hasattr(context, "_query_start_time"):
        return

    elapsed = time.perf_counter() - getattr(context, "_query_start_time")

    # 获取配置 (带有默认值防止报错)
    slow_threshold = getattr(setting, "SLOW_SQL_THRESHOLD", 0.5)
    is_debug = getattr(setting, "DEBUG", False)

    if elapsed > slow_threshold:
        sql_str = _get_formatted_sql(context, statement, parameters)
        logger.warning(f"SLOW SQL ({elapsed:.4f}s): {sql_str}")
    elif is_debug:
        sql_str = _get_formatted_sql(context, statement, parameters)
        logger.info(f"SQL ({elapsed:.4f}s): {sql_str}")


def _get_formatted_sql(context, statement, parameters) -> str:
    try:
        if context and context.compiled:
            return context.compiled.statement.compile(
                dialect=context.dialect,
                compile_kwargs={"literal_binds": True}
            )
        if parameters:
            return f"{statement} | Params: {parameters}"
        return str(statement)
    except Exception as e:
        return f"SQL_FORMAT_ERROR: {e} | Raw: {statement}"
