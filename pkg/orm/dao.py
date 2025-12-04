from sqlalchemy import Subquery
from sqlalchemy.orm import InstrumentedAttribute

from pkg.orm.base import SessionProvider
from pkg.orm.builder import QueryBuilder, new_cls_querier, new_sub_querier, CountBuilder, new_counter, new_col_counter, \
    UpdateBuilder, new_cls_updater, new_ins_updater
from pkg.orm.model_mixin import ModelMixin, MixinModelType


class BaseDao:
    _model_cls: type[ModelMixin] = None

    def __init__(self, *, session_provider: SessionProvider):
        if session_provider is None:
            raise ValueError("session_provider is required")

        self._session_provider = session_provider

    @property
    def model_cls(self) -> type[ModelMixin]:
        return self._model_cls

    def create(self, **kwargs) -> MixinModelType:
        return self._model_cls.create(**kwargs)

    @property
    def querier(self) -> QueryBuilder:
        return new_cls_querier(
            self._model_cls, session_provider=self._session_provider, include_deleted=False
        ).desc_(self._model_cls.updated_at)

    @property
    def querier_inc_deleted(self) -> QueryBuilder:
        return new_cls_querier(
            self._model_cls, session_provider=self._session_provider, include_deleted=True
        ).desc_(self._model_cls.updated_at)

    @property
    def querier_unsorted(self) -> QueryBuilder:
        return new_cls_querier(self._model_cls, session_provider=self._session_provider, include_deleted=False)

    @staticmethod
    def querier_inc_deleted_unsorted(self) -> QueryBuilder:
        return new_cls_querier(self._model_cls, session_provider=self._session_provider, include_deleted=True)

    def sub_querier(self, subquery: Subquery) -> QueryBuilder:
        return new_sub_querier(self._model_cls, session_provider=self._session_provider, subquery=subquery)

    @property
    def counter(self) -> CountBuilder:
        return new_counter(self._model_cls, session_provider=self._session_provider, include_deleted=False)

    @property
    def counter_inc_deleted(self) -> CountBuilder:
        return new_counter(self._model_cls, session_provider=self._session_provider, include_deleted=True)

    def col_counter(self, count_column: InstrumentedAttribute, *, is_distinct: bool = False) -> CountBuilder:
        return new_col_counter(
            self._model_cls,
            count_column=count_column,
            is_distinct=is_distinct,
            session_provider=self._session_provider,
            include_deleted=False
        )

    @property
    def updater(self) -> UpdateBuilder:
        return new_cls_updater(self._model_cls, session_provider=self._session_provider)

    def ins_updater(self, ins: ModelMixin) -> UpdateBuilder:
        return new_ins_updater(ins, session_provider=self._session_provider)

    async def query_by_id_or_none(
            self,
            primary_id: int,
            *,
            creator_id: int = None,
            include_deleted: bool = False
    ) -> MixinModelType:
        if include_deleted:
            querier = self.querier_inc_deleted.eq_(self._model_cls.id, primary_id)
        else:
            querier = self.querier.eq_(self._model_cls.id, primary_id)

        if creator_id and self._model_cls.has_creator_id_column():
            querier = self.querier.where(
                self._model_cls.get_creator_id_column() == creator_id
            )

        return await querier.first(include_deleted=include_deleted)

    async def query_by_id_or_exec(
            self,
            primary_id: int,
            *,
            creator_id: int = None,
            include_deleted: bool = False
    ) -> MixinModelType:
        ins = await self.query_by_id_or_none(primary_id, creator_id=creator_id, include_deleted=include_deleted)
        if not ins:
            raise Exception(f"{self._model_cls.__name__} not found for oid={primary_id}")
        return ins

    async def query_by_ids(self, ids: list[int]) -> list[MixinModelType]:
        return await self.querier.in_(self._model_cls.id, ids).all()

"""
使用示例：
class UserDao(BaseDao):
    _model_cls: type[User] = User

    def init_by_phone(self, phone: str, creator_id: int = 1) -> User:
        return self.create(phone=phone, creator_id=creator_id)

    async def get_user_by_phone(self, phone: str) -> User:
        return await self.querier.where(self._model_cls.phone == phone).first()


user_dao = UserDao(session_provider=get_session)
user_dao.init_by_phone(phone='+91', creator_id=1)

"""
