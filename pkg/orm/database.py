from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, TypeVar, cast, Optional

from sqlalchemy import (
    BigInteger, DateTime, ColumnExpressionArgument, Delete, Select, Subquery, Update, distinct, func, or_, select,
    update, insert, inspect
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, async_sessionmaker, AsyncEngine
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, InstrumentedAttribute, aliased
)
from sqlalchemy.sql.elements import ClauseElement, ColumnElement

from pkg import orjson_dumps, orjson_loads_types, orjson_loads, get_utc_without_tzinfo, unique_list
from pkg.context import ctx
from pkg.snowflake_tool import generate_snowflake_id

# ==============================================================================
# 1. 基础配置 (Base Configuration)
# ==============================================================================

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


# ==============================================================================
# 2. 模型定义 (Model Mixin)
# ==============================================================================

class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类"""
    pass


class ModelMixin(Base):
    """
    通用模型 Mixin，包含 ID、审计字段及通用 CRUD 方法
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

    # --- 核心逻辑 ---

    @classmethod
    def _prepare_create_data(cls, raw_data: dict[str, Any]) -> dict[str, Any]:
        """准备创建数据：注入ID、Context、时间戳，并过滤非数据库字段"""
        data = raw_data.copy()
        cur_datetime = get_utc_without_tzinfo()

        data.setdefault("created_at", cur_datetime)
        data.setdefault("updated_at", cur_datetime)

        if "id" not in data:
            data["id"] = generate_snowflake_id()

        if cls.has_creator_id_column() and "creator_id" not in data:
            user_id = ctx.get_user_id()
            if user_id is not None:
                data["creator_id"] = user_id

        if cls.has_updater_id_column() and "updater_id" not in data:
            data["updater_id"] = None

        valid_cols = set(cls.get_column_names())
        return {k: v for k, v in data.items() if k in valid_cols}

    # --- 批量操作 ---

    @classmethod
    async def insert_batch(cls, *, items: list[dict[str, Any]], session_provider: SessionProvider) -> None:
        """高性能批量插入 (Core Insert)"""
        if not items:
            return
        db_values = [cls._prepare_create_data(item) for item in items]
        try:
            async with session_provider() as sess:
                async with sess.begin():
                    await sess.execute(insert(cls).values(db_values))
        except Exception as e:
            raise RuntimeError(f"{cls.__name__} insert_batch failed: {e}") from e

    @classmethod
    async def add_batch(cls, ins_list: Sequence["ModelMixin"], session_provider: SessionProvider) -> None:
        """基于实例的批量插入"""
        if not ins_list:
            return
        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add_all(ins_list)
        except Exception as e:
            raise RuntimeError(f"{cls.__name__} add_batch failed: {e}") from e

    # --- 实例操作 ---

    async def save(self, session_provider: SessionProvider) -> None:
        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add(self)
        except Exception as e:
            raise RuntimeError(f"{self.__class__.__name__} save error: {e}") from e

    async def update(self, session_provider: SessionProvider, **kwargs) -> None:
        for column_name, value in kwargs.items():
            if not self.has_column(column_name):
                continue
            setattr(self, column_name, value)

        if self.has_updated_at_column():
            setattr(self, self.updated_at_column_name(), get_utc_without_tzinfo())

        if self.has_updater_id_column():
            setattr(self, self.updater_id_column_name(), ctx.get_user_id())

        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add(self)
        except Exception as e:
            raise RuntimeError(f"{self.__class__.__name__} update error: {e}") from e

    async def soft_delete(self, session_provider: SessionProvider) -> None:
        if self.has_deleted_at_column():
            await self.update(session_provider, **{self.deleted_at_column_name(): get_utc_without_tzinfo()})

    # --- 工厂与工具方法 ---

    @classmethod
    def create(cls, **kwargs) -> "ModelMixin":
        clean_kwargs = cls._prepare_create_data(kwargs)
        return cls(**clean_kwargs)

    def to_dict(self, *, exclude_column: list[str] = None) -> dict[str, Any]:
        return {
            col: getattr(self, col)
            for col in self.get_column_names()
            if not exclude_column or col not in exclude_column
        }

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


# ==============================================================================
# 3. 查询构建器 (Query Builder)
# ==============================================================================

class BaseBuilder[T: ModelMixin]:
    """SQL查询构建器基类"""
    __slots__ = ("_model_cls", "_stmt", "_session_provider")

    def __init__(self, model_cls: type[T], *, session_provider: SessionProvider):
        self._model_cls: type[T] = model_cls
        self._stmt: Select | Delete | Update | None = None
        self._session_provider = session_provider

    # --- 条件构造 ---
    def where(self, *conditions: ClauseElement) -> "BaseBuilder[T]":
        if conditions: self._stmt = self._stmt.where(*conditions)
        return self

    def eq_(self, column: InstrumentedAttribute | Mapped, value: Any) -> "BaseBuilder[T]":
        return self.where(column == value)

    def ne_(self, column: InstrumentedAttribute, value: Any) -> "BaseBuilder[T]":
        return self.where(column != value)

    def gt_(self, column: InstrumentedAttribute, value: Any) -> "BaseBuilder[T]":
        return self.where(column > value)

    def lt_(self, column: InstrumentedAttribute, value: Any) -> "BaseBuilder[T]":
        return self.where(column < value)

    def ge_(self, column: InstrumentedAttribute, value: Any) -> "BaseBuilder[T]":
        return self.where(column >= value)

    def le_(self, column: InstrumentedAttribute, value: Any) -> "BaseBuilder[T]":
        return self.where(column <= value)

    def in_(self, column: InstrumentedAttribute | Mapped, values: list | tuple) -> "BaseBuilder[T]":
        unique = unique_list(values, exclude_none=True)
        if len(unique) == 1: return self.where(column == unique[0])
        return self.where(column.in_(unique))

    def like(self, column: InstrumentedAttribute, pattern: str) -> "BaseBuilder[T]":
        return self.where(column.like(f"%{pattern}%"))

    def is_null(self, column: InstrumentedAttribute) -> "BaseBuilder[T]":
        return self.where(column.is_(None))

    def or_(self, *conditions: ColumnElement[bool]) -> "BaseBuilder[T]":
        return self.where(or_(*conditions)) if conditions else self

    # --- 排序与分组 ---
    def distinct_(self, *cols: InstrumentedAttribute) -> "BaseBuilder[T]":
        self._stmt = self._stmt.distinct(*cols)
        return self

    def desc_(self, col: InstrumentedAttribute | Mapped) -> "BaseBuilder[T]":
        self._stmt = self._stmt.order_by(col.desc())
        return self

    def asc_(self, col: InstrumentedAttribute) -> "BaseBuilder[T]":
        self._stmt = self._stmt.order_by(col.asc())
        return self

    def _apply_delete_at_is_none(self) -> None:
        if deleted_column := self._model_cls.get_column_or_none(self._model_cls.deleted_at_column_name()):
            self._stmt = self._stmt.where(deleted_column.is_(None))


class QueryBuilder[T: ModelMixin](BaseBuilder[T]):
    def __init__(self, model_cls: type[T], *, session_provider: SessionProvider,
                 initial_where: ColumnExpressionArgument | None = None,
                 custom_stmt: Select | None = None, include_deleted: bool | None = None):
        super().__init__(model_cls, session_provider=session_provider)

        self._stmt = custom_stmt if custom_stmt is not None else select(self._model_cls)

        if include_deleted is False and self._model_cls.has_deleted_at_column:
            self._apply_delete_at_is_none()
        if initial_where is not None:
            self._stmt = self._stmt.where(initial_where)

    @property
    def select_stmt(self) -> Select:
        return self._stmt

    def limit(self, limit: int) -> "QueryBuilder[T]":
        self._stmt = self._stmt.limit(limit)
        return self

    def paginate(self, *, page: int | None = None, limit: int | None = None) -> "QueryBuilder[T]":
        if page and limit: self._stmt = self._stmt.offset((page - 1) * limit).limit(limit)
        return self

    async def all(self) -> list[T]:
        async with self._session_provider() as sess:
            result = await sess.execute(self._stmt)
            return cast(list[T], result.scalars().all())

    async def first(self) -> T | None:
        async with self._session_provider() as sess:
            result = await sess.execute(self._stmt)
            return cast(T | None, result.scalars().first())


class CountBuilder[T: ModelMixin](BaseBuilder[T]):
    def __init__(self, model_cls: type[T], *, session_provider: SessionProvider,
                 count_column: InstrumentedAttribute = None, is_distinct: bool = False,
                 include_deleted: bool = None):
        super().__init__(model_cls, session_provider=session_provider)
        col = count_column if count_column is not None else self._model_cls.id
        expr = func.count(distinct(col)) if is_distinct else func.count(col)
        self._stmt = select(expr)

        if include_deleted is False and self._model_cls.has_deleted_at_column():
            self._apply_delete_at_is_none()

    async def count(self) -> int:
        async with self._session_provider() as sess:
            return (await sess.execute(self._stmt)).scalar()


class UpdateBuilder[T: ModelMixin](BaseBuilder[T]):
    def __init__(self, *, model_cls: type[T] | None = None, model_ins: T | None = None,
                 session_provider: SessionProvider):
        target_cls = model_cls if model_cls is not None else model_ins.__class__
        super().__init__(target_cls, session_provider=session_provider)
        self._stmt = update(self._model_cls)
        self._update_dict = {}
        if model_ins is not None:
            self._stmt = self._stmt.where(self._model_cls.id == model_ins.id)

    def update(self, **kwargs) -> "UpdateBuilder[T]":
        for k, v in kwargs.items():
            if self._model_cls.has_column(k):
                if isinstance(v, datetime) and v.tzinfo: v = v.replace(tzinfo=None)
                self._update_dict[k] = v
        return self

    def soft_delete(self) -> "UpdateBuilder[T]":
        if self._model_cls.has_deleted_at_column():
            self._update_dict[self._model_cls.deleted_at_column_name()] = get_utc_without_tzinfo()
        return self

    @property
    def update_stmt(self) -> Update:
        if not self._update_dict: return self._stmt

        # 自动处理 updated_at 和 deleted_at 同步
        updated_col = self._model_cls.updated_at_column_name()
        deleted_col = self._model_cls.deleted_at_column_name()

        if deleted_col in self._update_dict:
            self._update_dict.setdefault(updated_col, self._update_dict[deleted_col])
        self._update_dict.setdefault(updated_col, get_utc_without_tzinfo())

        if self._model_cls.has_updater_id_column():
            self._update_dict.setdefault(self._model_cls.updater_id_column_name(), ctx.get_user_id())

        return self._stmt.values(**self._update_dict).execution_options(synchronize_session=False)

    async def execute(self):
        if not self._update_dict: return
        async with self._session_provider() as sess:
            await sess.execute(self.update_stmt)
            await sess.commit()


# ==============================================================================
# 4. 数据访问对象 (DAO)
# ==============================================================================

class BaseDao[T: ModelMixin]:
    _model_cls: type[T] = None

    def __init__(self, *, session_provider: SessionProvider):
        if not self._model_cls:
            raise ValueError(f"DAO {self.__class__.__name__} must define _model_cls")
        self._session_provider = session_provider

    @property
    def model_cls(self) -> type[T]:
        return self._model_cls

    def create(self, **kwargs) -> T:
        return self._model_cls.create(**kwargs)

    @property
    def querier(self) -> QueryBuilder[T]:
        # 使用 cast 强制转换类型，消除类型检查器的报错
        return QueryBuilder(
            self._model_cls,
            session_provider=self._session_provider,
            include_deleted=False
        ).desc_(self._model_cls.updated_at)

    @property
    def querier_inc_deleted(self) -> QueryBuilder[T]:
        return QueryBuilder(
            self._model_cls,
            session_provider=self._session_provider,
            include_deleted=True
        ).desc_(self._model_cls.updated_at)

    @property
    def querier_unsorted(self) -> QueryBuilder[T]:
        return QueryBuilder(self._model_cls, session_provider=self._session_provider, include_deleted=False)

    @property
    def querier_inc_deleted_unsorted(self) -> QueryBuilder[T]:
        return QueryBuilder(self._model_cls, session_provider=self._session_provider, include_deleted=True)

    def sub_querier(self, subquery: Subquery) -> QueryBuilder[T]:
        alias = aliased(self._model_cls, subquery)
        return QueryBuilder(self._model_cls, session_provider=self._session_provider, custom_stmt=select(alias))

    # --- Counters ---
    @property
    def counter(self) -> CountBuilder[T]:
        return CountBuilder(self._model_cls, session_provider=self._session_provider, include_deleted=False)

    def col_counter(self, count_column: InstrumentedAttribute, *, is_distinct: bool = False) -> CountBuilder[T]:
        return CountBuilder(self._model_cls, session_provider=self._session_provider, count_column=count_column,
                            is_distinct=is_distinct, include_deleted=False)

    # --- Updaters ---
    @property
    def updater(self) -> UpdateBuilder[T]:
        return UpdateBuilder(model_cls=self._model_cls, session_provider=self._session_provider)

    def ins_updater(self, ins: T) -> UpdateBuilder[T]:
        return UpdateBuilder(model_ins=ins, session_provider=self._session_provider)

    # --- Common Methods ---
    async def query_by_id_or_none(
            self,
            primary_id: int,
            *, creator_id: int = None,
            include_deleted: bool = False
    ) -> T | None:
        qb = self.querier_inc_deleted if include_deleted else self.querier
        qb = qb.eq_(self._model_cls.id, primary_id)
        if creator_id and self._model_cls.has_creator_id_column():
            qb = qb.where(self._model_cls.get_creator_id_column() == creator_id)
        return await qb.first()

    async def query_by_ids(self, ids: list[int]) -> list[T]:
        return await self.querier.in_(self._model_cls.id, ids).all()
