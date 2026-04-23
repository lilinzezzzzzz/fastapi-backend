from internal.infra.database import get_read_session, get_session
from internal.models.user import User
from pkg.database.dao import BaseDao


class UserDao(BaseDao[User]):
    _model_cls: type[User] = User

    async def get_by_phone(self, phone: str) -> User | None:
        # 建议方法名更加简洁，因为已经在 UserDao 里了，不用写 get_user_by_phone
        # 使用你构建的 querier
        return await self.querier.eq_(self.model_cls.phone, phone).first()

    async def get_by_username(self, username: str) -> User | None:
        """根据用户名查询用户"""
        return await self.querier.eq_(self.model_cls.username, username).first()

    async def is_phone_exist(self, phone: str) -> bool:
        # 利用 first() 查询，找到一条就返回，比 count() 更高效
        user = await self.querier.eq_(self.model_cls.phone, phone).first()
        return user is not None


# 全局单例（懒加载）
_user_dao: UserDao | None = None


def new_user_dao() -> UserDao:
    global _user_dao
    if _user_dao is None:
        _user_dao = UserDao(
            session_provider=get_session,
            read_session_provider=get_read_session,
        )
    return _user_dao
