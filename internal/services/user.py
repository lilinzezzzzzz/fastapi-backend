from fastapi import Request

from internal.dao.user import user_dao
from internal.models.user import User


class UserService:
    @staticmethod
    async def get_user_by_phone(request: Request) -> User:
        # user_dao.querier(User).filter(User.id == 1).first()
        user = await user_dao.get_user_by_phone(request.state.phone)
        return user


async def new_user_service() -> UserService:
    return UserService()
