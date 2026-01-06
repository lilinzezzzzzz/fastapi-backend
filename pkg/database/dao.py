from collections.abc import Awaitable, Callable

from sqlalchemy import Subquery, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased

from pkg.database.base import ModelMixin, SessionProvider
from pkg.database.builder import CountBuilder, QueryBuilder, UpdateBuilder

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


async def execute_transaction(
    session_provider: SessionProvider,
    callback: Callable[[AsyncSession], Awaitable[None]],
    autoflush: bool = True,
) -> None:
    """
        [Transaction] 手动事务执行器：通过回调函数在同一个事务中执行复杂逻辑。

        该方法解决了简单的批量执行无法处理 "先插入获取ID，再使用ID插入关联表" 的逻辑依赖问题。
        它会自动开启事务，并在回调执行完毕后提交；如果发生异常则自动回滚。

        Args:
            session_provider: Session 提供者
            callback: 包含业务逻辑的异步函数。接收当前事务的 `AsyncSession`。
            autoflush: 是否自动刷新（默认 True）。如果在事务中需要立即获取自增 ID，请保持为 True。

        Raises:
            RuntimeError: 当事务执行失败时抛出，并包含原始异常信息。

        Examples:
            **场景 1：简单的混合操作**
            ```python
            async def _do_work(sess: AsyncSession) -> None:
                # 1. ORM 添加
                sess.add(User(name="Alice"))
                # 2. SQL 执行
                await sess.execute(update(Log).where(...))

            await execute_transaction(session_provider, _do_work)
            ```

            **场景 2：有逻辑依赖的操作 (先插后查/后改)**
            *注意：需要调用 await sess.flush() 来获取生成的 ID*
            ```python
            async def _create_order_flow(sess: AsyncSession) -> None:
                # 1. 创建主订单
                order = Order(user_id=1, amount=100)
                sess.add(order)

                # [关键] 刷新到数据库以获取自增 ID (此时并未 commit)
                await sess.flush()

                # 2. 使用生成的 ID 创建子项
                item = OrderItem(order_id=order.id, product="Apple")
                sess.add(item)

            await execute_transaction(session_provider, _create_order_flow)
            ```
        """
    try:
        async with session_provider(autoflush=autoflush) as sess:
            async with sess.begin():
                await callback(sess)
    except Exception as e:
        raise RuntimeError(f"Transaction failed: {e}") from e
