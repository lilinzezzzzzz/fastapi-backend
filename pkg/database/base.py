from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Any, Optional, TypeVar

from sqlalchemy import BigInteger, DateTime, Insert, insert, inspect, Executable
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, InstrumentedAttribute

from pkg import async_context
from pkg.snowflake import snowflake_id_generator

from pkg.toolkit.json import orjson_dumps, orjson_loads_types, orjson_loads
from pkg.toolkit.time import utc_now_naive

SessionProvider = Callable[..., AbstractAsyncContextManager[AsyncSession]]


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
        json_deserializer: Callable[[orjson_loads_types], Any] = orjson_loads
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
        json_deserializer=json_deserializer
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

    async def save(
            self, session_provider: SessionProvider | None = None, execute: bool = True
    ) -> Insert | None:
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

    # ==========================================================================
    # 字段补全辅助方法
    # ==========================================================================

    @staticmethod
    def _get_context_defaults() -> ContextDefaults:
        return ContextDefaults(
            now=utc_now_naive(),
            user_id=async_context.get_user_id()
        )

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
            stmt: Executable,
            session_provider: SessionProvider | None,
            execute: bool,
            error_context: str
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
    def get_column_or_none(cls, column_name: str) -> Optional[InstrumentedAttribute]:
        return getattr(cls, column_name, None)

    @classmethod
    def get_creator_id_column(cls) -> Optional[InstrumentedAttribute]:
        return cls.get_column_or_none(cls.creator_id_column_name())


MixinModelType = TypeVar("MixinModelType", bound=ModelMixin)
