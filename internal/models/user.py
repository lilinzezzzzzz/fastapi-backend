from sqlalchemy import Column, String

from pkg.orm.model_mixin import ModelMixin


class User(ModelMixin):
    __tablename__ = "user"

    username = Column(String(64))
    account = Column(String(64))
    phone = Column(String(11))
