from internal.dao.user import UserDao, user_dao
from internal.models.user import User


class UserService:
    def __init__(self, dao: UserDao):
        self._user_dao = dao

    @staticmethod
    async def hello_world():
        return "Hello World"

    async def get_user_by_phone(self, phone: str) -> User:
        # 建议直接传参数，而不是传 request 对象，这样 Service 更纯粹，更容易测试
        return await self._user_dao.get_by_phone(phone)


def new_user_service() -> UserService:
    """依赖注入函数，返回 Service 单例"""
    return UserService(user_dao)
