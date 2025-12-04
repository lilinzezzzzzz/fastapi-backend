from typing import ClassVar

from internal.infra.database import get_session
from internal.models.user import User
from pkg.orm.database import BaseDao


class UserDao(BaseDao[User]):
    _model_cls: type[User] = User

    async def get_by_phone(self, phone: str) -> User | None:
        # 建议方法名更加简洁，因为已经在 UserDao 里了，不用写 get_user_by_phone
        # 使用你构建的 querier
        return await self.querier.eq_(User.phone, phone).first()

    async def is_phone_exist(self, phone: str) -> bool:
        # 利用你封装的 count
        count = await self.counter.eq_(User.phone, phone).count()
        return count > 0


# 单例模式 (Singleton)
# 在简单的应用中，直接实例化一个全局 dao 是没问题的
# 因为 session_provider 是一个工厂函数，不会在 import 时建立连接
user_dao = UserDao(session_provider=get_session)
