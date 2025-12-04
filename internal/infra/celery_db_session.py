from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from internal.config.setting import setting
from pkg import orjson_dumps, orjson_loads
from pkg.orm.base import new_async_engine, new_async_session_maker

# 进程内单例（不要在模块导入时构造）
_engine: AsyncEngine | None = None
_SessionMaker: async_sessionmaker[AsyncSession] | None = None


def init_async_celery_db():
    """
    在【当前进程】初始化异步引擎和 Session 工厂。
    - FastAPI 进程：应用启动时调用一次
    - Celery worker 子进程：worker_process_init 信号里调用一次
    """
    global _engine, _SessionMaker
    if _engine is not None:
        return  # 幂等

    _engine = new_async_engine(
        database_uri=setting.sqlalchemy_database_uri,
        echo=setting.sqlalchemy_echo,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=1800,
        json_serializer=orjson_dumps,
        json_deserializer=orjson_loads
    )
    _SessionMaker = new_async_session_maker(engine=_engine)


def _ensure_initialized() -> async_sessionmaker[AsyncSession]:
    if _SessionMaker is None:
        raise RuntimeError(
            "Async DB is not initialized in this process. "
            "Call init_async_db(...) during process startup."
        )
    return _SessionMaker


@asynccontextmanager
async def get_celery_session(*, autoflush: bool = True) -> AsyncGenerator[AsyncSession, Any]:
    """
    和你现有的 get_session 兼容：每次使用一个独立 AsyncSession。
    """
    session_maker = _ensure_initialized()

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


async def close_async_celery_db() -> None:
    """
    进程关闭前可调用，优雅释放连接池。
    """
    global _engine, _SessionMaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _SessionMaker = None
