from sqlalchemy import Subquery, select, Executable
from sqlalchemy.orm import aliased, InstrumentedAttribute

from pkg.async_database.base import ModelMixin, SessionProvider
from pkg.async_database.builder import QueryBuilder, CountBuilder, UpdateBuilder

"""
数据访问对象 (DAO)
"""

class BaseDao[T: ModelMixin]:
    _model_cls: type[T] = None  # 类型提示

    def __init__(self, *, session_provider: SessionProvider, model_cls: type[T] = None):
        """
        修复了 __init__ 逻辑：
        1. 先赋值 session_provider
        2. 再判断 model_cls 参数
        3. 最后判断 类属性 _model_cls
        """
        self._session_provider = session_provider

        # 1. 优先使用构造函数传入的 model_cls
        if model_cls:
            self._model_cls = model_cls

        # 2. 如果没传，检查是否在类定义中设置了 _model_cls
        # 使用 getattr 防止 AttributeError
        elif not getattr(self, "_model_cls", None):
            raise ValueError(f"DAO {self.__class__.__name__} must define _model_cls or pass it to __init__")

    @property
    def model_cls(self) -> type[T]:
        return self._model_cls

    def create(self, **kwargs) -> T:
        return self._model_cls.create(**kwargs)

    @property
    def querier(self) -> QueryBuilder[T]:
        return QueryBuilder(
            self._model_cls,
            session_provider=self._session_provider,
            include_deleted=False
        ).desc_(self._model_cls.updated_at)

    @property
    def querier_inc_deleted(self) -> QueryBuilder[T]:
        return QueryBuilder(
            self._model_cls,
            session_provider=self._session_provider,
            include_deleted=True
        ).desc_(self._model_cls.updated_at)

    @property
    def querier_unsorted(self) -> QueryBuilder[T]:
        return QueryBuilder(self._model_cls, session_provider=self._session_provider, include_deleted=False)

    @property
    def querier_inc_deleted_unsorted(self) -> QueryBuilder[T]:
        return QueryBuilder(self._model_cls, session_provider=self._session_provider, include_deleted=True)

    def sub_querier(self, subquery: Subquery) -> QueryBuilder[T]:
        alias = aliased(self._model_cls, subquery)
        return QueryBuilder(self._model_cls, session_provider=self._session_provider, custom_stmt=select(alias))

    # --- Counters ---
    @property
    def counter(self) -> CountBuilder[T]:
        return CountBuilder(self._model_cls, session_provider=self._session_provider, include_deleted=False)

    def col_counter(self, count_column: InstrumentedAttribute, *, is_distinct: bool = False) -> CountBuilder[T]:
        return CountBuilder(self._model_cls, session_provider=self._session_provider, count_column=count_column,
                            is_distinct=is_distinct, include_deleted=False)

    # --- Updaters ---
    @property
    def updater(self) -> UpdateBuilder[T]:
        return UpdateBuilder(model_cls=self._model_cls, session_provider=self._session_provider)

    def ins_updater(self, ins: T) -> UpdateBuilder[T]:
        return UpdateBuilder(model_ins=ins, session_provider=self._session_provider)

    # --- Common Methods ---
    async def query_by_primary_id(
            self,
            primary_id: int,
            *,
            creator_id: int = None,
            include_deleted: bool = False
    ) -> T | None:
        qb = self.querier_inc_deleted if include_deleted else self.querier
        qb = qb.eq_(self._model_cls.id, primary_id)
        if creator_id and self._model_cls.has_creator_id_column():
            qb = qb.where(self._model_cls.get_creator_id_column() == creator_id)
        return await qb.first()

    async def query_by_ids(self, ids: list[int]) -> list[T]:
        return await self.querier.in_(self._model_cls.id, ids).all()


async def execute_transaction_atomic(
        session_provider: SessionProvider,
        autoflush: bool = True,
        *stmts: Executable | None
) -> None:
    """
    [Transaction] 在同一个事务中原子性地执行多个 SQL 语句。
    会自动过滤掉 None 的语句（例如当 insert_instances 没有数据返回 None 时）。
    """
    # 过滤掉 None (比如空列表调用 insert_instances 返回的 None)
    valid_stmts = [s for s in stmts if s is not None]

    if not valid_stmts:
        return

    try:
        async with session_provider(autoflush=autoflush) as sess:
            async with sess.begin():
                for stmt in valid_stmts:
                    await sess.execute(stmt)
    except Exception as e:
        raise RuntimeError(f"Atomic execution failed: {e}") from e
