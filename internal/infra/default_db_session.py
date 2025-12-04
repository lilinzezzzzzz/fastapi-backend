import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from internal.config.setting import setting
from pkg import orjson_dumps, orjson_loads
from pkg.logger_tool import logger
from pkg.orm.base import new_async_engine, new_async_session_maker

# 创建异步引擎
engine = new_async_engine(
    database_uri=setting.sqlalchemy_database_uri,
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
session_maker = new_async_session_maker(engine=engine)


@asynccontextmanager
async def get_session(autoflush: bool = True) -> AsyncGenerator[AsyncSession, Any]:
    async with session_maker() as session:
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


def _get_formatted_sql(context, statement, parameters) -> str:
    """
    辅助函数：统一处理 SQL 格式化逻辑 (兼容 MySQL 和 PG)
    """
    try:
        # 1. 优先尝试使用 SQLAlchemy 的 Compiler
        if context and context.compiled:
            return context.compiled.statement.compile(
                dialect=context.dialect,
                compile_kwargs={"literal_binds": True}
            )

        # 2. 回退处理：手动展示
        if parameters:
            return f"{statement} | Params: {parameters}"
        return str(statement)
    except Exception as e:
        return f"SQL_FORMAT_ERROR: {e} | Raw: {statement}"


def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """
    只做一件事：记录开始时间。
    极轻量，不影响性能。
    """
    if context:
        # 直接给 context 对象动态添加一个属性，这是 Python 的黑魔法，但在这里非常标准且好用
        setattr(context, "_query_start_time", time.perf_counter())


def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """
    处理日志逻辑：计算耗时 -> 判断条件 -> 格式化 SQL -> 打印
    """
    if not context or not hasattr(context, "_query_start_time"):
        return

    # 计算耗时
    elapsed = time.perf_counter() - getattr(context, "_query_start_time")
    # 定义判断逻辑
    is_slow = elapsed > getattr(setting, "SLOW_SQL_THRESHOLD", 0.5)
    is_debug = getattr(setting, "DEBUG", False)

    # 场景 1: 慢查询 (无论生产还是开发环境，都记录为 Warning)
    if is_slow:
        sql_str = _get_formatted_sql(context, statement, parameters)
        logger.warning(f"SLOW SQL ({elapsed:.4f}s): {sql_str}")

    # 场景 2: 开发环境 (记录所有普通查询为 Info，排除掉刚才已经记过的慢查询)
    elif is_debug:
        sql_str = _get_formatted_sql(context, statement, parameters)
        logger.info(f"SQL ({elapsed:.4f}s): {sql_str}")


# 注册事件
event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
event.listen(engine.sync_engine, "after_cursor_execute", after_cursor_execute)
