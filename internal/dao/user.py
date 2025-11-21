from internal.dao import BaseDao
from internal.infra.celery_db_session import get_celery_session
from internal.infra.default_db_session import get_session
from internal.models.user import User


class UserDao(BaseDao):
    _model_cls: type[User] = User

    def init_by_phone(self, phone: str, creator_id: int = 1) -> User:
        return self.create(phone=phone, creator_id=creator_id)

    async def get_user_by_phone(self, phone: str) -> User:
        return await self.querier.where(self._model_cls.phone == phone).first()


user_dao = UserDao(session_provider=get_session)
celery_user_dao = UserDao(session_provider=get_celery_session)