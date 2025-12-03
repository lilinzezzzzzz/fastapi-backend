from datetime import datetime
from typing import TypeVar, Optional, Any, Sequence

from sqlalchemy import BigInteger, DateTime, inspect
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    InstrumentedAttribute
)
# 假设这些 pkg 包保持不变
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
    注意：Mixin 不应该继承 DeclarativeBase，它应该作为普通类混入到最终模型中。
    例如：class User(ModelMixin, Base): ...
    """
    __abstract__ = True

    # --- 1. 使用 Mapped + mapped_column 定义字段 (SQLAlchemy 2.0 风格) ---

    # 主键：自动推断为必填
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # 必填字段
    creator_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))

    # 可空字段 (使用 | None 或 Optional)
    # default=None, server_default=None 在 2.0 中通常不需要显式写，除非有特殊数据库层面的默认值
    updater_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)

    # --- 2. 批量操作方法 ---

    @classmethod
    async def add_all_dict(
            cls,
            items: list[dict[str, Any]],
            session_provider: SessionProvider
    ) -> None:
        if not items:
            return

        # 使用 cls.create 统一处理 snowflake id 和 context 注入
        ins_list = [cls.create(**item) for item in items]

        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add_all(ins_list)
        except Exception as e:
            # 建议使用具体异常或记录日志后抛出
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
        """保存当前实例"""
        try:
            async with session_provider() as sess:
                async with sess.begin():  # 显式开启事务
                    sess.add(self)
        except Exception as e:
            raise RuntimeError(f"{self.__class__.__name__} save error: {e}") from e

    async def update(self, session_provider: SessionProvider, **kwargs) -> None:
        """更新当前实例"""
        # 1. 更新普通字段
        for column_name, value in kwargs.items():
            if not self.has_column(column_name):
                continue
            setattr(self, column_name, value)

        # 2. 自动更新 updated_at
        if self.has_updated_at_column():
            setattr(self, self.updated_at_column_name(), get_utc_without_tzinfo())

        # 3. 自动更新 updater_id (从上下文获取)
        if self.has_updater_id_column():
            user_id = ctx.get_user_id()
            # 确保 user_id 类型正确或为 None
            setattr(self, self.updater_id_column_name(), user_id)

        # 4. 提交数据库
        try:
            async with session_provider() as sess:
                async with sess.begin():
                    # merge 通常比 add 更安全，防止对象已经 detach
                    # 但如果你确定对象是新建的或者 attach 的，add 也可以
                    sess.add(self)
        except Exception as e:
            raise RuntimeError(f"{self.__class__.__name__} update error: {e}") from e

    async def soft_delete(self, session_provider: SessionProvider) -> None:
        """软删除 (注意：需要传入 session_provider)"""
        await self.update(
            session_provider,
            **{self.deleted_at_column_name(): get_utc_without_tzinfo()}
        )

    # --- 4. 核心工厂方法 ---

    @classmethod
    def create(cls, **kwargs) -> "ModelMixin":
        """
        工厂方法：创建实例并注入 ID 和 Context 信息
        注意：此方法仅在内存中创建对象，未持久化到 DB
        """
        cur_datetime = get_utc_without_tzinfo()

        # 准备初始化参数
        init_kwargs = {
            "created_at": cur_datetime,
            "updated_at": cur_datetime
        }

        # 处理 ID (Snowflake)
        if "id" not in kwargs:
            init_kwargs["id"] = generate_snowflake_id()

        # 处理 creator_id
        if cls.has_creator_id_column():
            # 优先使用 kwargs 中的，如果没有则从 context 获取
            if "creator_id" in kwargs:
                init_kwargs["creator_id"] = kwargs.pop("creator_id")
            else:
                user_id = ctx.get_user_id()
                if user_id is not None:
                    init_kwargs["creator_id"] = user_id

        # 处理 updater_id (创建时通常为空，或者同 creator)
        if cls.has_updater_id_column():
            # 确保显式设置为 None 或根据业务需求处理
            init_kwargs["updater_id"] = None

        # 合并用户传入的参数 (优先级最高，覆盖前面的默认值)
        init_kwargs.update(kwargs)

        # 实例化 (SQLAlchemy 2.0 Base 默认接受 **kwargs)
        ins = cls(**init_kwargs)

        # 如果 kwargs 里有不在 columns 里的垃圾数据，Base 默认的 __init__ 可能会报错
        # 如果需要过滤，可以使用 cls.populate 逻辑，但 Base(**kwargs) 性能更好
        return ins

    def populate(self, **kwargs):
        """填充属性，忽略不存在的字段"""
        for column_name, value in kwargs.items():
            if not self.has_column(column_name):
                continue
            setattr(self, column_name, value)

    def to_dict(self, *, exclude_column: list[str] = None) -> dict[str, Any]:
        """序列化为字典"""
        exclude_set = set(exclude_column) if exclude_column else set()

        # 使用 SQLAlchemy inspect 2.0 方式获取列属性，更稳健
        return {
            c.key: getattr(self, c.key)
            for c in inspect(self.__class__).mapper.column_attrs
            if c.key not in exclude_set
        }

    def clone(self) -> "ModelMixin":
        """克隆当前对象（排除审计字段）"""
        excluded_columns = {"updater_id", "creator_id", "updated_at", "deleted_at", "id"}
        data = self.to_dict(exclude_column=list(excluded_columns))
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
        """判断字段是否存在于 Table 定义中"""
        return column_name in cls.__table__.columns

    @classmethod
    def get_column_names(cls) -> list[str]:
        return list(cls.__table__.columns.keys())

    @classmethod
    def get_column_or_none(cls, column_name: str) -> InstrumentedAttribute | None:
        return getattr(cls, column_name, None)

    @classmethod
    def get_column_or_raise(cls, column_name: str) -> InstrumentedAttribute:
        if column_name not in cls.__table__.columns:
            raise ValueError(
                f"{column_name} is not a real table column of {cls.__name__}"
            )
        return getattr(cls, column_name)

    @classmethod
    def get_creator_id_column(cls) -> Optional[InstrumentedAttribute]:
        return cls.get_column_or_none(cls.creator_id_column_name())


MixinModelType = TypeVar("MixinModelType", bound=ModelMixin)
