from collections.abc import Callable
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
    通用模型 Mixin
    优化点：
    1. save 只做 INSERT，update 只做 UPDATE
    2. 字段补全逻辑统一，减少冗余代码
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
    # 1. 工厂与批量操作
    # ==========================================================================

    @classmethod
    def create(cls, **kwargs) -> "ModelMixin":
        """
        创建一个新的、填充好默认值的实例（Transient 状态）。
        """
        # 1. 过滤参数
        valid_cols = set(cls.get_column_names())
        clean_kwargs = {k: v for k, v in kwargs.items() if k in valid_cols}

        # 2. 实例化
        ins = cls(**clean_kwargs)

        # 3. 补全字段 (ID, Time, Context)
        ins._fill_insert_fields()

        return ins

    @classmethod
    async def insert(cls, *, items: list[dict[str, Any]], session_provider: SessionProvider) -> None:
        """
        高性能批量插入 (Core Insert)。
        会自动补全 ID, created_at, updated_at, creator_id 等。
        """
        if not items:
            return

        # 获取一次公共默认值，稍微提升循环效率
        defaults = cls._get_context_defaults()

        # 处理每一条数据
        db_values = [cls._prepare_batch_data(item, defaults) for item in items]

        try:
            async with session_provider() as sess:
                async with sess.begin():
                    await sess.execute(insert(cls).values(db_values))
        except Exception as e:
            raise RuntimeError(f"{cls.__name__} insert failed: {e}") from e

    # ==========================================================================
    # 2. 实例操作 (CRUD)
    # ==========================================================================

    async def save(self, session_provider: SessionProvider) -> None:
        """
        [Strict Insert] 仅用于保存新对象。
        如果是新对象 -> Core Insert (高性能)
        如果是旧对象 -> 抛出异常 (强制使用 update)
        """
        state = inspect(self)

        # 严格检查：只有 Transient (临时/新建) 对象允许 save
        if not state.transient:
            raise RuntimeError(
                f"save() is strictly for INSERT operations. "
                f"Object {self.__class__.__name__}(id={self.id}) is already persistent/detached. "
                f"Please use update() instead."
            )

        # 1. 确保字段补全 (防止用户是手动 User() 而非 create() 出来的)
        self._fill_insert_fields()

        # 2. 提取纯字典
        data = self._extract_db_values()

        # 3. 执行 Core Insert
        try:
            async with session_provider() as sess:
                async with sess.begin():
                    await sess.execute(insert(self.__class__).values(data))
        except Exception as e:
            raise RuntimeError(f"{self.__class__.__name__} save(insert) error: {e}") from e

    async def update(self, session_provider: SessionProvider, **kwargs) -> None:
        """
        [Update] 更新对象。自动处理 updated_at 和 updater_id。
        """
        # 1. 设置传入的属性
        for column_name, value in kwargs.items():
            if self.has_column(column_name):
                setattr(self, column_name, value)

        # 2. 补全更新追踪字段 (Time, Updater)
        self._fill_update_fields()

        # 3. 使用 Session.add 触发 ORM Update
        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add(self)
        except Exception as e:
            raise RuntimeError(f"{self.__class__.__name__} update error: {e}") from e

    async def soft_delete(self, session_provider: SessionProvider) -> None:
        if self.has_deleted_at_column():
            # 复用 update 逻辑，它会自动处理 updated_at
            await self.update(session_provider, **{self.deleted_at_column_name(): get_utc_without_tzinfo()})

    # ==========================================================================
    # 3. 内部辅助方法 (Logic Optimization)
    # ==========================================================================

    @staticmethod
    def _get_context_defaults() -> dict[str, Any]:
        """[内部] 获取当前上下文的通用默认值 (时间, 用户ID, 雪花ID)"""
        return {
            "now": get_utc_without_tzinfo(),
            "user_id": ctx.get_user_id(),
            "new_id": generate_snowflake_id()
        }

    def _fill_insert_fields(self):
        """[Instance] 插入前补全实例字段"""
        defaults = self._get_context_defaults()

        # ID
        if not self.id:
            self.id = defaults["new_id"]

        # Time
        if not self.created_at:
            self.created_at = defaults["now"]
        if not self.updated_at:
            self.updated_at = defaults["now"]

        # Context
        if self.has_creator_id_column() and not self.creator_id and defaults["user_id"]:
            self.creator_id = defaults["user_id"]

        if self.has_updater_id_column() and not self.updater_id:
            # 新建时 updater 可以为空，或者跟 creator 一致，视业务而定，这里留空
            self.updater_id = None

    def _fill_update_fields(self):
        """[Instance] 更新前补全实例字段"""
        if self.has_updated_at_column():
            setattr(self, self.updated_at_column_name(), get_utc_without_tzinfo())

        if self.has_updater_id_column():
            setattr(self, self.updater_id_column_name(), ctx.get_user_id())

    @classmethod
    def _prepare_batch_data(cls, raw_data: dict[str, Any], defaults: dict[str, Any] = None) -> dict[str, Any]:
        """[Dict] 准备批量插入的数据字典"""
        data = raw_data.copy()
        if defaults is None:
            defaults = cls._get_context_defaults()

        # Time
        data.setdefault("created_at", defaults["now"])
        data.setdefault("updated_at", defaults["now"])

        # ID
        if "id" not in data:
            data["id"] = generate_snowflake_id()  # 批量时每个ID必须不同，不能复用 defaults['new_id']

        # Context
        if cls.has_creator_id_column() and "creator_id" not in data and defaults["user_id"]:
            data["creator_id"] = defaults["user_id"]

        if cls.has_updater_id_column() and "updater_id" not in data:
            data["updater_id"] = None

        # Filter Columns
        valid_cols = set(cls.get_column_names())
        return {k: v for k, v in data.items() if k in valid_cols}

    def _extract_db_values(self) -> dict[str, Any]:
        """[Instance -> Dict] 提取实例数据用于 Core Insert"""
        values = {}
        mapper = inspect(self.__class__)
        valid_cols = set(self.get_column_names())

        for col_name in valid_cols:
            # 仅提取已加载/已赋值的属性
            if hasattr(self, col_name):
                val = getattr(self, col_name)
                values[col_name] = val
        return values

    def to_dict(self, *, exclude_column: list[str] = None) -> dict[str, Any]:
        return {
            col: getattr(self, col)
            for col in self.get_column_names()
            if not exclude_column or col not in exclude_column
        }

    # ==========================================================================
    # 4. 反射与元数据工具
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
    async def query_by_primary_id(
            self,
            primary_id: int,
            *,
            creator_id: int = None,
            include_deleted: bool = False
    ) -> T | None:
        qb = self.querier_inc_deleted if include_deleted else self.querier
        qb = qb.eq_(self._model_cls.id, primary_id)
        if creator_id and self._model_cls.has_creator_id_column():
            qb = qb.where(self._model_cls.get_creator_id_column() == creator_id)
        return await qb.first()

    async def query_by_ids(self, ids: list[int]) -> list[T]:
        return await self.querier.in_(self._model_cls.id, ids).all()
