from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Executable, Insert, Text, insert, inspect
from sqlalchemy.dialects import oracle, postgresql
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, Mapped, mapped_column
from sqlalchemy.types import JSON as SA_JSON, TypeDecorator

from pkg.toolkit import context
from pkg.toolkit.inter import snowflake_id_generator
from pkg.toolkit.json import JsonInputType, orjson_dumps, orjson_loads
from pkg.toolkit.timer import utc_now_naive

SessionProvider = Callable[..., AbstractAsyncContextManager[AsyncSession]]


class JSONType(TypeDecorator):
    """
    跨数据库兼容的 JSON 类型。

    - PostgreSQL: 使用原生 JSONB 类型（支持索引）
    - MySQL 5.7+: 使用原生 JSON 类型
    - Oracle 21c+: 使用原生 JSON 类型（oracle_native_json=True）
    - Oracle 12c-20c: 使用 CLOB + 手动序列化/反序列化（oracle_native_json=False）
    - 其他数据库: 使用 TEXT + 手动序列化/反序列化

    用法示例:
        # 默认模式（Oracle 使用 CLOB，兼容 12c+）
        class MyModel(ModelMixin):
            metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
            config: Mapped[list] = mapped_column(JSONType, default=list)

        # Oracle 21c+ 原生 JSON 模式
        class MyModel21c(ModelMixin):
            data: Mapped[dict] = mapped_column(JSONType(oracle_native_json=True), default=dict)
    """

    impl = Text
    cache_ok = True

    def __init__(self, oracle_native_json: bool = False) -> None:
        """
        Args:
            oracle_native_json: Oracle 是否使用原生 JSON 类型
                - True: Oracle 21c+ 原生 JSON（性能更好，支持 JSON 函数）
                - False: Oracle 12c+ CLOB 存储（兼容性更好）
        """
        super().__init__()
        self.oracle_native_json = oracle_native_json

    def load_dialect_impl(self, dialect: Dialect):
        """根据数据库类型选择底层实现"""
        if dialect.name == "postgresql":
            # PostgreSQL 使用 JSONB（支持索引和 JSON 操作符）
            return dialect.type_descriptor(postgresql.JSONB())
        elif dialect.name == "mysql":
            # MySQL 5.7+ 支持原生 JSON
            return dialect.type_descriptor(SA_JSON())
        elif dialect.name == "oracle":
            if self.oracle_native_json:
                # Oracle 21c+ 原生 JSON 类型
                return dialect.type_descriptor(oracle.JSON())
            else:
                # Oracle 12c-20c 使用 CLOB 存储
                return dialect.type_descriptor(oracle.CLOB())
        else:
            # 其他数据库使用 TEXT
            return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """写入数据库时：Python 对象 -> JSON 字符串"""
        if value is None:
            return None
        # 原生 JSON 类型不需要手动序列化
        if dialect.name in ("postgresql", "mysql"):
            return value
        if dialect.name == "oracle" and self.oracle_native_json:
            return value
        return orjson_dumps(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        """从数据库读取时：JSON 字符串 -> Python 对象"""
        if value is None:
            return None
        # 原生 JSON 类型已自动反序列化
        if dialect.name in ("postgresql", "mysql"):
            return value
        if dialect.name == "oracle" and self.oracle_native_json:
            return value
        if isinstance(value, (dict, list)):
            return value
        return orjson_loads(value)


def new_async_engine(
    *,
    database_uri: str,
    echo: bool = True,
    pool_pre_ping: bool = True,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_timeout: int = 30,
    pool_recycle: int = 1800,
    json_serializer: Callable[[Any], str] = orjson_dumps,
    json_deserializer: Callable[[JsonInputType], Any] = orjson_loads,
) -> AsyncEngine:
    return create_async_engine(
        url=database_uri,
        echo=echo,
        pool_pre_ping=pool_pre_ping,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        json_serializer=json_serializer,
        json_deserializer=json_deserializer,
    )


def new_async_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=True)


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类"""

    pass


@dataclass(frozen=True, slots=True)
class ContextDefaults:
    now: datetime
    user_id: int | None


class ModelMixin(Base):
    """
    通用模型 Mixin
    """

    __abstract__ = True

    # --- 字段定义 ---
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    creator_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))

    updater_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

    # ==========================================================================
    # 工厂方法
    # ==========================================================================

    @classmethod
    def create(cls, **kwargs) -> "ModelMixin":
        """
        创建一个新的、填充好默认值的实例（Transient 状态）。
        """
        valid_cols = set(cls.get_column_names())
        clean_kwargs = {k: v for k, v in kwargs.items() if k in valid_cols}

        ins = cls(**clean_kwargs)
        ins._fill_ins_insert_fields()
        return ins

    # ==========================================================================
    # 批量操作 (Batch)
    # ==========================================================================

    @classmethod
    async def insert_rows(
        cls, *, rows: list[dict[str, Any]], session_provider: SessionProvider, execute: bool = True
    ) -> Insert | None:
        """[Batch Dict] 高性能批量插入字典。"""
        if not rows:
            return None

        defaults = cls._get_context_defaults()
        db_values = [cls._fill_dict_insert_fields(row, defaults) for row in rows]

        stmt = insert(cls).values(db_values)

        if not execute:
            return stmt

        return await cls._execute_or_return(
            stmt, session_provider, execute, error_context=f"{cls.__name__} insert_rows"
        )

    @classmethod
    async def insert_instances(
        cls,
        *,
        items: list["ModelMixin"],
        session_provider: SessionProvider | None = None,
        execute: bool = True,
    ) -> Insert | None:
        """
        [Batch Instance] 高性能批量插入对象实例。

        Args:
            items: 要插入的实例列表
            session_provider: 会话提供者（execute=True 时必填）
            execute: 是否执行 SQL，False 时仅返回 Insert 语句

        Returns:
            execute=False 时返回 Insert 语句，否则返回 None
        """
        if not items:
            return None

        db_values = []
        for ins in items:
            ins._fill_ins_insert_fields()
            db_values.append(ins._extract_db_values())

        stmt = insert(cls).values(db_values)

        return await cls._execute_or_return(
            stmt, session_provider, execute, error_context=f"{cls.__name__} insert_instances"
        )

    # ==========================================================================
    # 单例操作 (CRUD)
    # ==========================================================================

    async def save(self, session_provider: SessionProvider | None = None, execute: bool = True) -> Insert | None:
        """[Strict Insert] 仅用于保存新对象。"""
        state = inspect(self)

        if not state.transient:
            raise RuntimeError(
                f"save() is strictly for INSERT operations. "
                f"Object {self.__class__.__name__}(id={self.id}) is already persistent/detached. "
                f"Please use update() instead."
            )

        self._fill_ins_insert_fields()
        data = self._extract_db_values()

        stmt = insert(self.__class__).values(data)

        return await self._execute_or_return(
            stmt, session_provider, execute, error_context=f"{self.__class__.__name__} save(insert)"
        )

    async def update(self, session_provider: SessionProvider | None = None, **kwargs) -> None:
        """[Strict Update] 仅用于更新已存在的对象。"""
        state = inspect(self)

        if state.transient:
            raise RuntimeError(
                f"update() is strictly for UPDATE operations on existing records. "
                f"Object {self.__class__.__name__} is new (transient). "
                f"Please use save() or insert_instances() first."
            )

        for column_name, value in kwargs.items():
            if self.has_column(column_name):
                setattr(self, column_name, value)

        self._fill_ins_update_fields()

        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add(self)
        except Exception as e:
            raise RuntimeError(f"{self.__class__.__name__} update error: {e}") from e

    async def soft_delete(self, session_provider: SessionProvider) -> None:
        if self.has_deleted_at_column():
            # update 方法会自动调用 _fill_ins_update_fields 处理 updated_at
            await self.update(session_provider, **{self.deleted_at_column_name(): utc_now_naive()})

    async def restore(self, session_provider: SessionProvider) -> None:
        """
        [Soft Delete] 恢复已删除的对象
        """
        if self.has_deleted_at_column():
            # 恢复时：
            # 1. deleted_at 设为 None
            # 2. update() 会自动将 updated_at 设为当前时间（符合逻辑，因为数据状态变了）
            await self.update(session_provider, **{self.deleted_at_column_name(): None})

    # ==========================================================================
    # 字段补全辅助方法
    # ==========================================================================

    @staticmethod
    def _get_context_defaults() -> ContextDefaults:
        return ContextDefaults(now=utc_now_naive(), user_id=context.get_user_id())

    def _fill_ins_insert_fields(self):
        """[Instance Insert] 补全实例插入所需的字段"""
        defaults = self._get_context_defaults()

        if not self.id:
            self.id = snowflake_id_generator.generate()

        if not self.created_at:
            self.created_at = defaults.now
        if not self.updated_at:
            self.updated_at = defaults.now

        if self.has_creator_id_column() and not self.creator_id and defaults.user_id:
            self.creator_id = defaults.user_id

        if self.has_updater_id_column() and not self.updater_id:
            self.updater_id = None

    def _fill_ins_update_fields(self):
        """[Instance Update] 补全实例更新所需的字段"""
        defaults = self._get_context_defaults()

        if self.has_updated_at_column():
            setattr(self, self.updated_at_column_name(), defaults.now)

        if self.has_updater_id_column():
            setattr(self, self.updater_id_column_name(), defaults.user_id)

    @classmethod
    def _fill_dict_insert_fields(cls, raw_data: dict[str, Any], defaults: ContextDefaults) -> dict[str, Any]:
        """[Dict Insert] 补全字典插入所需的字段"""
        data = raw_data.copy()

        data.setdefault("created_at", defaults.now)
        data.setdefault("updated_at", defaults.now)

        if "id" not in data:
            data["id"] = snowflake_id_generator.generate()

        if cls.has_creator_id_column() and "creator_id" not in data and defaults.user_id:
            data["creator_id"] = defaults.user_id

        if cls.has_updater_id_column() and "updater_id" not in data:
            data["updater_id"] = None

        valid_cols = set(cls.get_column_names())
        return {k: v for k, v in data.items() if k in valid_cols}

    def _extract_db_values(self) -> dict[str, Any]:
        """[Instance -> Dict]"""
        values = {}
        valid_cols = set(self.get_column_names())
        for col_name in valid_cols:
            if hasattr(self, col_name):
                values[col_name] = getattr(self, col_name)
        return values

    @staticmethod
    async def _execute_or_return(
        stmt: Executable, session_provider: SessionProvider | None, execute: bool, error_context: str
    ) -> Executable | None:
        """
        统一处理 SQL 语句的执行逻辑：
        - 如果 execute=False，直接返回语句对象。
        - 如果 execute=True，校验 session_provider 并执行事务。
        """
        if not execute:
            return stmt

        if session_provider is None:
            raise ValueError(f"session_provider is required when execute=True ({error_context})")

        try:
            async with session_provider() as sess:
                async with sess.begin():
                    await sess.execute(stmt)
        except Exception as e:
            raise RuntimeError(f"{error_context} failed: {e}") from e

        return None

    def to_dict(self, *, exclude_column: list[str] = None) -> dict[str, Any]:
        return {
            col: getattr(self, col)
            for col in self.get_column_names()
            if not exclude_column or col not in exclude_column
        }

    # ==========================================================================
    # 反射与元数据工具
    # ==========================================================================

    @staticmethod
    def updater_id_column_name() -> str:
        return "updater_id"

    @staticmethod
    def creator_id_column_name() -> str:
        return "creator_id"

    @staticmethod
    def updated_at_column_name() -> str:
        return "updated_at"

    @staticmethod
    def deleted_at_column_name() -> str:
        return "deleted_at"

    @classmethod
    def has_deleted_at_column(cls) -> bool:
        return cls.has_column(cls.deleted_at_column_name())

    @classmethod
    def has_updated_at_column(cls) -> bool:
        return cls.has_column(cls.updated_at_column_name())

    @classmethod
    def has_creator_id_column(cls) -> bool:
        return cls.has_column(cls.creator_id_column_name())

    @classmethod
    def has_updater_id_column(cls) -> bool:
        return cls.has_column(cls.updater_id_column_name())

    @classmethod
    def has_column(cls, column_name: str) -> bool:
        return column_name in inspect(cls).columns

    @classmethod
    def get_column_names(cls) -> list[str]:
        return list(inspect(cls).columns.keys())

    @classmethod
    def get_column_or_none(cls, column_name: str) -> InstrumentedAttribute | None:
        return getattr(cls, column_name, None)

    @classmethod
    def get_creator_id_column(cls) -> InstrumentedAttribute | None:
        return cls.get_column_or_none(cls.creator_id_column_name())
