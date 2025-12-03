from datetime import datetime
from typing import TypeVar, Optional, Any, Sequence

from sqlalchemy import BigInteger, DateTime, inspect
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
    使用 inspect(cls) 替代直接访问 cls.__table__，解决了 IDE 无法识别 Mixin 中 table 属性的问题。
    """
    __abstract__ = True

    # --- 1. 字段定义 (SQLAlchemy 2.0 Mapped 风格) ---

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    creator_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))

    # 可空字段，使用 Python 原生类型提示 | None
    updater_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

    # --- 2. 批量操作方法 ---

    @classmethod
    async def add_all_dict(
            cls,
            items: list[dict[str, Any]],
            session_provider: SessionProvider
    ) -> None:
        if not items:
            return

        # 统一使用 create 方法实例化，确保 ID 和 Context 逻辑生效
        ins_list = [cls.create(**item) for item in items]
        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add_all(ins_list)
        except Exception as e:
            raise RuntimeError(f"{cls.__name__} add_all_dict failed: {e}") from e

    @classmethod
    async def add_all_ins(
            cls,
            ins_list: Sequence["ModelMixin"],
            session_provider: SessionProvider
    ) -> None:
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
        """软删除：需传入 session_provider"""
        await self.update(
            session_provider,
            **{self.deleted_at_column_name(): get_utc_without_tzinfo()}
        )

    # --- 4. 工厂方法与序列化 ---

    @classmethod
    def create(cls, **kwargs) -> "ModelMixin":
        """工厂方法：负责注入 ID、时间、Context 信息"""
        cur_datetime = get_utc_without_tzinfo()

        # 预设初始化参数
        init_kwargs: dict[str, Any] = {
            "created_at": cur_datetime,
            "updated_at": cur_datetime
        }

        # 注入 Snowflake ID
        if "id" not in kwargs:
            init_kwargs["id"] = generate_snowflake_id()

        # 注入 creator_id
        if cls.has_creator_id_column():
            if "creator_id" in kwargs:
                init_kwargs["creator_id"] = kwargs.pop("creator_id")
            else:
                user_id = ctx.get_user_id()
                if user_id is not None:
                    init_kwargs["creator_id"] = user_id

        # 注入 updater_id
        if cls.has_updater_id_column():
            init_kwargs["updater_id"] = None

        # 合并用户参数 (覆盖默认值)
        init_kwargs.update(kwargs)

        # 实例化对象
        # 注意：这里会调用 DeclarativeBase 默认的 __init__，它接受 **kwargs
        # 为了避免传入非数据库字段报错，我们可以在这里做一层过滤，或者信任 kwargs 准确
        # 如果需要严格过滤，可以启用下面的逻辑：
        valid_cols = cls.get_column_names()
        clean_kwargs = {k: v for k, v in init_kwargs.items() if k in valid_cols}
        return cls(**clean_kwargs)

    def populate(self, **kwargs):
        for column_name, value in kwargs.items():
            if not self.has_column(column_name):
                continue
            setattr(self, column_name, value)

    def to_dict(self, *, exclude_column: list[str] = None) -> dict[str, Any]:
        d = {}
        # get_column_names 内部现在使用了 inspect，所以这里也是安全的
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

    # --- 5. 辅助 / 反射方法 (使用 inspect 替代 __table__) ---

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

    # --- 重点修改区域：使用 inspect ---

    @classmethod
    def has_column(cls, column_name: str) -> bool:
        """
        判断是否为真实数据库字段
        使用 inspect(cls).columns 替代 cls.__table__.columns
        """
        mapper = inspect(cls)
        # inspect(cls) 在运行时对映射类调用时返回 Mapper 对象
        # Mapper.columns 是一个 ColumnCollection
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
