from typing import Annotated

from fastapi import Depends

from internal.dao.user import UserDao
from internal.models.user import User


class UserService:
    # FastAPI 会自动处理这里的 Depends
    def __init__(self, dao: Annotated[UserDao, Depends()]):
        self._user_dao = dao

    @staticmethod
    async def hello_world():
        return "Hello World"

    async def get_user_by_phone(self, phone: str) -> User:
        # 建议直接传参数，而不是传 request 对象，这样 Service 更纯粹，更容易测试
        return await self._user_dao.get_by_phone(phone)


def new_user_service() -> UserService:
    return UserService()
