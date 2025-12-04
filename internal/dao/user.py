from internal.infra.database import get_session
from internal.models.user import User
from pkg.orm.database import BaseDao, SessionProvider


class UserDao(BaseDao):
    _model_cls: type[User] = User

    def __init__(self, *, session_provider: SessionProvider):
        super().__init__(session_provider=session_provider, model_cls=self._model_cls)

    def init_by_phone(self, phone: str, creator_id: int = 1) -> User:
        return self.create(phone=phone, creator_id=creator_id)

    async def get_user_by_phone(self, phone: str) -> User:
        return await self.querier.where(self._model_cls.phone == phone).first()


user_dao = UserDao(session_provider=get_session)
