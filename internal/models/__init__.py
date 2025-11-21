"""该目录主要用于数据库模型"""
from typing import TypeVar

from sqlalchemy import BigInteger, Column, DateTime
from sqlalchemy.orm import InstrumentedAttribute

from internal.infra.default_db_session import Base, get_session
from pkg import get_utc_without_tzinfo
from pkg.context_tool import get_user_id_context_var
from pkg.snowflake_tool import generate_snowflake_id
from pkg.types import SessionProvider


class ModelMixin(Base):
    __abstract__ = True

    id = Column(BigInteger, primary_key=True)
    creator_id = Column(BigInteger, nullable=False)
    updater_id = Column(BigInteger, nullable=True, default=None, server_default=None)
    created_at = Column(DateTime(timezone=False), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True, default=None, server_default=None)
    deleted_at = Column(DateTime(timezone=False), nullable=True, default=None, server_default=None)

    @classmethod
    async def add_all_dict(
            cls,
            items: list[dict],
            session_provider: SessionProvider = get_session
    ):
        if not items:
            return

        ins_list = [cls.create(**item) for item in items]
        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add_all(ins_list)
        except Exception as e:
            raise Exception(f"{cls.__name__} add_all_dict failed, error={e}")

    @classmethod
    async def add_all_ins(
            cls,
            ins_list: list["ModelMixin"],
            session_provider: SessionProvider = get_session
    ):
        if not ins_list:
            return

        try:
            async with session_provider() as sess:
                async with sess.begin():
                    sess.add_all(ins_list)
        except Exception as e:
            raise Exception(f"{cls.__name__} add_all_ins failed, error={e}")

    async def save(self, session_provider: SessionProvider = get_session):
        try:
            async with session_provider() as sess:
                sess.add(self)
                await sess.commit()
        except Exception as e:
            raise Exception(f"{self.__class__.__name__} save error: {e}")

    async def update(
            self,
            session_provider: SessionProvider = get_session,
            **kwargs
    ):
        for column_name, value in kwargs.items():
            if not self.has_column(column_name):
                continue
            setattr(self, column_name, value)

        if hasattr(self, self.updated_at_column_name()):
            cur_datetime = get_utc_without_tzinfo()
            setattr(self, self.updated_at_column_name(), cur_datetime)

        if self.has_updater_id_column():
            user_id = get_user_id_context_var()
            setattr(self, self.updater_id_column_name(), user_id)

        try:
            async with session_provider() as sess:
                sess.add(self)
                await sess.commit()
        except Exception as e:
            raise Exception(f"{self.__class__.__name__} update error: {e}")

    async def soft_delete(self):
        await self.update(
            **{self.deleted_at_column_name(): get_utc_without_tzinfo()}
        )

    @classmethod
    def create(cls, **kwargs) -> "ModelMixin":
        cur_datetime = get_utc_without_tzinfo()
        ins = cls(created_at=cur_datetime, updated_at=cur_datetime)

        if "id" not in kwargs:
            ins.id = generate_snowflake_id()
        if ins.has_creator_id_column() and getattr(ins, ins.creator_id_column_name()) is not None:
            user_id = get_user_id_context_var()
            setattr(ins, ins.creator_id_column_name(), user_id)
        if ins.has_updater_id_column():
            setattr(ins, ins.updater_id_column_name(), None)

        ins.populate(**kwargs)
        return ins

    def populate(self, **kwargs):
        for column_name, value in kwargs.items():
            if not self.has_column(column_name):
                # logger.warning(f"Column '{column_name}' does not exist in model '{self.__class__.__name__}'")
                continue
            setattr(self, column_name, value)

    def to_dict(self, *, exclude_column: list[str] = None) -> dict:
        d = {}
        for column_name in self.get_column_names():
            if exclude_column and column_name in exclude_column:
                continue

            val = getattr(self, column_name)
            d[column_name] = val
        return d

    def clone(self) -> "ModelMixin":
        excluded_columns = ["updater_id", "creator_id", "updated_at", "deleted_at", "id"]
        data = {k: v for k, v in self.to_dict().items() if k not in excluded_columns}
        return self.create(**data)

    def mixin_check_required_fields(self, fields: list[str]) -> tuple[str, bool]:
        for field in fields:
            val = getattr(self, field)
            if not val:
                return field, False
        return "", True

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
        """判断是否有删除时间字段"""
        return cls.has_column(cls.deleted_at_column_name())

    @classmethod
    def has_updated_at_column(cls):
        return cls.has_column(cls.updated_at_column_name())

    @classmethod
    def has_creator_id_column(cls) -> bool:
        """判断是否有创建人字段"""
        return cls.has_column(cls.creator_id_column_name())

    @classmethod
    def has_updater_id_column(cls) -> bool:
        """判断是否有更新人字段"""
        return cls.has_column(cls.updater_id_column_name())

    @classmethod
    def has_column(cls, column_name: str) -> bool:
        """判断是否为真实数据库字段"""
        return column_name in cls.__table__.columns

    @classmethod
    def get_column_names(cls) -> list[str]:
        return list(cls.__table__.columns.keys())

    @classmethod
    def get_column_or_none(cls, column_name: str) -> InstrumentedAttribute:
        return getattr(cls, column_name)

    @classmethod
    def get_column_or_raise(cls, column_name: str) -> InstrumentedAttribute:
        if column_name not in cls.__table__.columns:
            raise ValueError(
                f"{column_name} is not a real table column of {cls.__name__}"
            )
        return getattr(cls, column_name)

    @classmethod
    def get_creator_id_column(cls) -> InstrumentedAttribute:
        return cls.get_column_or_none(cls.creator_id_column_name())


MixinModelType = TypeVar("MixinModelType", bound=ModelMixin)  # 定义一个泛型变量 T，继承自 ModelMixin