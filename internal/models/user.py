from sqlalchemy import Column, String
from sqlalchemy.orm import Mapped, mapped_column

from pkg.orm.model_mixin import ModelMixin, Base


class User(Base, ModelMixin):
    __tablename__ = "user"

    username: Mapped[str] = mapped_column(String(64))
    account: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(11))
