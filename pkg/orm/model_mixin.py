from datetime import datetime
from typing import TypeVar, Optional, Any, Sequence

from sqlalchemy import BigInteger, DateTime, inspect, insert
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    InstrumentedAttribute
)

from pkg import get_utc_without_tzinfo
from pkg.context import ctx
from pkg.orm.types import SessionProvider
from pkg.snowflake_tool import generate_snowflake_id


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类"""
    pass


class ModelMixin:
    """
    通用模型 Mixin
    """
    __abstract__ = True

    # --- 1. 字段定义 (SQLAlchemy 2.0 Mapped 风格) ---

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    creator_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))

    # 可空字段
    updater_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

    # --- 新增：核心逻辑抽取 ---

    @classmethod
    def _prepare_create_data(cls, raw_data: dict[str, Any]) -> dict[str, Any]:
        """
        [核心逻辑] 准备创建数据：注入ID、Context、时间戳，并过滤非数据库字段
        返回：用于 insert 或 实例化的纯字典
        """
        # 1. 复制数据，避免修改引用
        data = raw_data.copy()

        cur_datetime = get_utc_without_tzinfo()

        # 2. 注入时间戳 (如果未传入)
        data.setdefault("created_at", cur_datetime)
        data.setdefault("updated_at", cur_datetime)

        # 3. 注入 Snowflake ID (如果未传入)
        if "id" not in data:
            data["id"] = generate_snowflake_id()

        # 4. 注入 creator_id (从 Context)
        if cls.has_creator_id_column() and "creator_id" not in data:
            user_id = ctx.get_user_id()
            if user_id is not None:
                data["creator_id"] = user_id

        # 5. 处理 updater_id (新建时通常为空，或者根据业务需求设置)
        if cls.has_updater_id_column() and "updater_id" not in data:
            data["updater_id"] = None

        # 6. 字段过滤：仅保留数据库存在的列
        # 这一步对于 insert 语句尤为重要，因为 insert 遇到未知列会报错
        valid_cols = set(cls.get_column_names())
        clean_data = {k: v for k, v in data.items() if k in valid_cols}

        return clean_data

    # --- 2. 批量操作方法 ---

    @classmethod
    async def add_all_dict(
            cls,
            items: list[dict[str, Any]],
            session_provider: SessionProvider
    ) -> None:
        """
        高性能批量插入 (SQLAlchemy Core Insert)
        """
        if not items:
            return

        # 1. 批量预处理数据 (注入 ID, Context 等)
        # 注意：这里不再实例化 ORM 对象，而是生成纯字典列表
        db_values = [cls._prepare_create_data(item) for item in items]

        try:
            async with session_provider() as sess:
                async with sess.begin():
                    # 2. 使用 Core Insert 语句
                    # 这比 session.add_all(instances) 快得多
                    stmt = insert(cls).values(db_values)
                    await sess.execute(stmt)

        except Exception as e:
            raise RuntimeError(f"{cls.__name__} add_all_dict (insert) failed: {e}") from e

    @classmethod
    async def add_all_ins(
            cls,
            ins_list: Sequence["ModelMixin"],
            session_provider: SessionProvider
    ) -> None:
        """
        基于实例的批量插入 (保持原样，因为输入已经是实例)
        """
        if not ins_list:
            return

        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add_all(ins_list)
        except Exception as e:
            raise RuntimeError(f"{cls.__name__} add_all_ins failed: {e}") from e

    # --- 3. 实例操作方法 ---

    async def save(self, session_provider: SessionProvider) -> None:
        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add(self)
        except Exception as e:
            raise RuntimeError(f"{self.__class__.__name__} save error: {e}") from e

    async def update(self, session_provider: SessionProvider, **kwargs) -> None:
        # 1. 更新传入的字段
        for column_name, value in kwargs.items():
            if not self.has_column(column_name):
                continue
            setattr(self, column_name, value)

        # 2. 自动处理更新时间
        if self.has_updated_at_column():
            setattr(self, self.updated_at_column_name(), get_utc_without_tzinfo())

        # 3. 自动处理更新人
        if self.has_updater_id_column():
            user_id = ctx.get_user_id()
            setattr(self, self.updater_id_column_name(), user_id)

        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add(self)
        except Exception as e:
            raise RuntimeError(f"{self.__class__.__name__} update error: {e}") from e

    async def soft_delete(self, session_provider: SessionProvider) -> None:
        await self.update(
            session_provider,
            **{self.deleted_at_column_name(): get_utc_without_tzinfo()}
        )

    # --- 4. 工厂方法与序列化 ---

    @classmethod
    def create(cls, **kwargs) -> "ModelMixin":
        """
        工厂方法：负责注入 ID、时间、Context 信息
        现已重构为调用 _prepare_create_data 以保持逻辑统一
        """
        # 1. 调用统一的数据预处理逻辑
        clean_kwargs = cls._prepare_create_data(kwargs)

        # 2. 实例化对象
        # 因为 _prepare_create_data 已经过滤了字段，这里直接解包非常安全
        return cls(**clean_kwargs)

    def populate(self, **kwargs):
        for column_name, value in kwargs.items():
            if not self.has_column(column_name):
                continue
            setattr(self, column_name, value)

    def to_dict(self, *, exclude_column: list[str] = None) -> dict[str, Any]:
        d = {}
        for column_name in self.get_column_names():
            if exclude_column and column_name in exclude_column:
                continue
            val = getattr(self, column_name)
            d[column_name] = val
        return d

    def clone(self) -> "ModelMixin":
        excluded_columns = ["updater_id", "creator_id", "updated_at", "deleted_at", "id"]
        data = self.to_dict(exclude_column=excluded_columns)
        return self.create(**data)

    def mixin_check_required_fields(self, fields: list[str]) -> tuple[str, bool]:
        for field in fields:
            val = getattr(self, field, None)
            if not val:
                return field, False
        return "", True

    # --- 5. 辅助 / 反射方法 ---

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
    def has_updated_at_column(cls):
        return cls.has_column(cls.updated_at_column_name())

    @classmethod
    def has_creator_id_column(cls) -> bool:
        return cls.has_column(cls.creator_id_column_name())

    @classmethod
    def has_updater_id_column(cls) -> bool:
        return cls.has_column(cls.updater_id_column_name())

    @classmethod
    def has_column(cls, column_name: str) -> bool:
        mapper = inspect(cls)
        return column_name in mapper.columns

    @classmethod
    def get_column_names(cls) -> list[str]:
        mapper = inspect(cls)
        return list(mapper.columns.keys())

    @classmethod
    def get_column_or_none(cls, column_name: str) -> Optional[InstrumentedAttribute]:
        return getattr(cls, column_name, None)

    @classmethod
    def get_column_or_raise(cls, column_name: str) -> InstrumentedAttribute:
        mapper = inspect(cls)
        if column_name not in mapper.columns:
            raise ValueError(
                f"{column_name} is not a real table column of {cls.__name__}"
            )
        return getattr(cls, column_name)

    @classmethod
    def get_creator_id_column(cls) -> Optional[InstrumentedAttribute]:
        return cls.get_column_or_none(cls.creator_id_column_name())


MixinModelType = TypeVar("MixinModelType", bound=ModelMixin)
