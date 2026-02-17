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
    _model_cls: type[T] | None = None  # 类型提示

    def __init__(
        self,
        *,
        session_provider: SessionProvider,
        read_session_provider: SessionProvider | None = None,
        model_cls: type[T] | None = None,
    ):
        """
        Args:
            session_provider: 写库 session 提供者（主库）
            read_session_provider: 读库 session 提供者（只读副本）。
                如果为 None，读操作自动 fallback 到写库的 session_provider。
            model_cls: 模型类，可通过构造函数传入或在子类中定义 _model_cls
        """
        self._session_provider = session_provider
        self._read_session_provider = read_session_provider or session_provider

        # 1. 优先使用构造函数传入的 model_cls
        if model_cls:
            self._model_cls = model_cls

        # 2. 如果没传，检查是否在类定义中设置了 _model_cls
        # 使用 getattr 防止 AttributeError
        elif not getattr(self, "_model_cls", None):
            raise ValueError(f"DAO {self.__class__.__name__} must define _model_cls or pass it to __init__")

    @property
    def model_cls(self) -> type[T]:
        if self._model_cls is None:
            raise ValueError(f"DAO {self.__class__.__name__} must define _model_cls or pass it to __init__")

        return self._model_cls

    def create(self, **kwargs) -> T:
        return self.model_cls.create(**kwargs)

    @property
    def querier(self) -> QueryBuilder[T]:
        return QueryBuilder(self.model_cls, session_provider=self._read_session_provider, include_deleted=False).desc_(
            self.model_cls.updated_at
        )

    @property
    def querier_inc_deleted(self) -> QueryBuilder[T]:
        return QueryBuilder(self.model_cls, session_provider=self._read_session_provider, include_deleted=True).desc_(
            self.model_cls.updated_at
        )

    @property
    def querier_unsorted(self) -> QueryBuilder[T]:
        return QueryBuilder(self.model_cls, session_provider=self._read_session_provider, include_deleted=False)

    @property
    def querier_inc_deleted_unsorted(self) -> QueryBuilder[T]:
        return QueryBuilder(self.model_cls, session_provider=self._read_session_provider, include_deleted=True)

    def sub_querier(self, subquery: Subquery) -> QueryBuilder[T]:
        alias = aliased(self.model_cls, subquery)
        return QueryBuilder(self.model_cls, session_provider=self._read_session_provider, custom_stmt=select(alias))

    # --- Write Queriers (强制读主库，用于写后读一致性场景) ---
    @property
    def write_querier(self) -> QueryBuilder[T]:
        """强制从主库查询（用于写后读一致性场景）"""
        return QueryBuilder(self.model_cls, session_provider=self._session_provider, include_deleted=False).desc_(
            self.model_cls.updated_at
        )

    @property
    def write_querier_unsorted(self) -> QueryBuilder[T]:
        """强制从主库查询，不排序"""
        return QueryBuilder(self.model_cls, session_provider=self._session_provider, include_deleted=False)

    # --- Counters ---
    @property
    def counter(self) -> CountBuilder[T]:
        return CountBuilder(self.model_cls, session_provider=self._read_session_provider, include_deleted=False)

    def col_counter(self, count_column: InstrumentedAttribute, *, is_distinct: bool = False) -> CountBuilder[T]:
        return CountBuilder(
            self.model_cls,
            session_provider=self._read_session_provider,
            count_column=count_column,
            is_distinct=is_distinct,
            include_deleted=False,
        )

    # --- Updaters ---
    @property
    def updater(self) -> UpdateBuilder[T]:
        return UpdateBuilder(model_cls=self.model_cls, session_provider=self._session_provider)

    def ins_updater(self, ins: T) -> UpdateBuilder[T]:
        return UpdateBuilder(model_ins=ins, session_provider=self._session_provider)

    # --- Common Methods ---
    async def query_by_primary_id(
        self, primary_id: int, *, creator_id: int = None, include_deleted: bool = False
    ) -> T | None:
        qb = self.querier_inc_deleted if include_deleted else self.querier
        qb = qb.eq_(self.model_cls.id, primary_id)
        if creator_id and self.model_cls.has_creator_id_column():
            qb = qb.where(self.model_cls.get_creator_id_column() == creator_id)
        return await qb.first()

    async def query_by_ids(self, ids: list[int]) -> list[T]:
        return await self.querier.in_(self.model_cls.id, ids).all()


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
        **场景 1：使用 UpdateBuilder 进行批量更新**
        ```python
        async def _batch_update(sess: AsyncSession) -> None:
            # 使用 UpdateBuilder 构建 SQL 语句
            updater = await dao.updater.eq_(
                Model.id, record_id
            ).update(
                status="active",
                execute=False,  # 不自动执行
            )
            # 在事务的 session 中执行
            await sess.execute(updater.update_stmt)

        await execute_transaction(session_provider, _batch_update)
        ```

        **场景 2：混合 ORM 和原生 SQL**
        ```python
        async def _mixed_operations(sess: AsyncSession) -> None:
            # 1. ORM 添加新对象
            new_user = User(name="Alice")
            sess.add(new_user)
            await sess.flush()  # 获取自增 ID

            # 2. 使用 UpdateBuilder 批量更新
            updater = await dao.updater.eq_(
                Log.user_id, new_user.id
            ).update(
                execute=False,
                status="processed",
            )
            await sess.execute(updater.update_stmt)

        await execute_transaction(session_provider, _mixed_operations)
        ```

        **场景 3：先插入后关联（使用雪花算法 ID）**
        ```python
        async def _create_with_relation(sess: AsyncSession) -> None:
            # 1. 创建主记录（ID 通过雪花算法预先生成）
            order = Order.create(user_id=1, amount=100)
            # order.id 已经有值，无需 flush

            # 2. 直接使用 order.id 创建子记录
            item = OrderItem.create(order_id=order.id, product="Apple")

            # 3. 一起添加到 session
            sess.add(order)
            sess.add(item)

        await execute_transaction(session_provider, _create_with_relation)
        ```

        **场景 4：数据库自增 ID（需要 flush）**
        *仅当使用数据库自增 ID 时需要此场景*
        ```python
        async def _create_with_auto_increment(sess: AsyncSession) -> None:
            # 1. 创建主记录（ID 由数据库自增生成）
            order = OtherModel(user_id=1, amount=100)
            sess.add(order)

            # [关键] 刷新到数据库以获取自增 ID（此时并未 commit）
            await sess.flush()

            # 2. 使用获取的 ID 创建子记录
            item = RelatedModel(other_id=order.id, product="Apple")
            sess.add(item)

        await execute_transaction(session_provider, _create_with_auto_increment)
        ```
    """
    try:
        async with session_provider(autoflush=autoflush) as sess:
            async with sess.begin():
                await callback(sess)
    except Exception as e:
        raise RuntimeError(f"Transaction failed: {e}") from e
