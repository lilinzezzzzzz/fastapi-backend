from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from pkg.database.base import ModelMixin


class User(ModelMixin):
    __tablename__ = "user"

    username: Mapped[str] = mapped_column(String(64), comment="用户名")
    account: Mapped[str] = mapped_column(String(64), comment="账号")
    phone: Mapped[str] = mapped_column(String(11), comment="手机号")
    password_hash: Mapped[str | None] = mapped_column(String(255), comment="密码哈希")

    # 第三方登录相关字段
    wechat_openid: Mapped[str | None] = mapped_column(
        String(128), comment="微信 OpenID", index=True, nullable=True
    )
    wechat_unionid: Mapped[str | None] = mapped_column(
        String(128), comment="微信 UnionID", index=True, nullable=True
    )
    wechat_avatar: Mapped[str | None] = mapped_column(
        String(512), comment="微信头像 URL", nullable=True
    )
    wechat_nickname: Mapped[str | None] = mapped_column(
        String(128), comment="微信昵称", nullable=True
    )
    alipay_user_id: Mapped[str | None] = mapped_column(
        String(128), comment="支付宝用户 ID", index=True, nullable=True
    )
    alipay_avatar: Mapped[str | None] = mapped_column(
        String(512), comment="支付宝头像 URL", nullable=True
    )
    alipay_nickname: Mapped[str | None] = mapped_column(
        String(128), comment="支付宝昵称", nullable=True
    )
