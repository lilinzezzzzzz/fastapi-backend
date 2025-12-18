from datetime import datetime
from typing import Any, Self

from sqlalchemy import ClauseElement, ColumnElement, Delete, Select, Update, distinct, func, or_, select, update
from sqlalchemy.orm import InstrumentedAttribute, Mapped

from pkg import async_context
from pkg.async_logger import logger
from pkg.database.base import ModelMixin, SessionProvider
from pkg.toolkit.list import unique_list
from pkg.toolkit.time import utc_now_naive

"""
构建器 (Builder)
"""


class BaseBuilder[T: ModelMixin]:
    """SQL查询构建器基类"""

    __slots__ = ("_model_cls", "_stmt", "_session_provider")

    def __init__(self, model_cls: type[T], *, session_provider: SessionProvider):
        self._model_cls: type[T] = model_cls
        self._stmt: Select | Delete | Update | None = None
        self._session_provider = session_provider

    # --- 条件构造 ---
    def where(self, *conditions: ClauseElement) -> Self:
        if conditions:
            self._stmt = self._stmt.where(*conditions)
        return self

    def apply_kwargs_filters(self, **kwargs):
        """将 kwargs 筛选条件应用到 builder（querier/counter/updater）

        Args:
            **kwargs: 字段名=值 的筛选条件

        Returns:
            应用了筛选条件的 builder

        Example:
            await builder.apply_kwargs_filters(dao.querier, organization_id=1, status="active").all()
            await builder.apply_kwargs_filters(dao.counter, organization_id=1).count()
        """
        for k, v in kwargs.items():
            if column := self._model_cls.get_column_or_none(k):
                self.where(column == v)
        return self

    def eq_(self, column: InstrumentedAttribute | Mapped, value: Any) -> Self:
        return self.where(column == value)

    def ne_(self, column: InstrumentedAttribute, value: Any) -> Self:
        return self.where(column != value)

    def gt_(self, column: InstrumentedAttribute, value: Any) -> Self:
        return self.where(column > value)

    def lt_(self, column: InstrumentedAttribute, value: Any) -> Self:
        return self.where(column < value)

    def ge_(self, column: InstrumentedAttribute, value: Any) -> Self:
        return self.where(column >= value)

    def le_(self, column: InstrumentedAttribute, value: Any) -> Self:
        return self.where(column <= value)

    def in_(self, column: InstrumentedAttribute | Mapped, values: list | tuple) -> Self:
        """
        修复了空列表逻辑：空列表应该返回 False 条件，而不是返回 self (忽略条件)。
        """
        if not values:
            raise ValueError(f"in_() func values cannot be empty for column {column}")

        unique = unique_list(values, exclude_none=True)

        if len(unique) == 1:
            return self.where(column == unique[0])

        return self.where(column.in_(unique))

    def like(self, column: InstrumentedAttribute, pattern: str) -> Self:
        return self.where(column.like(f"%{pattern}%"))

    def is_null(self, column: InstrumentedAttribute) -> Self:
        return self.where(column.is_(None))

    def or_(self, *conditions: ColumnElement[bool]) -> Self:
        return self.where(or_(*conditions)) if conditions else self

    # --- 排序与分组 ---
    def distinct_(self, *cols: InstrumentedAttribute) -> Self:
        self._stmt = self._stmt.distinct(*cols)
        return self

    def desc_(self, col: InstrumentedAttribute | Mapped) -> Self:
        self._stmt = self._stmt.order_by(col.desc())
        return self

    def asc_(self, col: InstrumentedAttribute) -> Self:
        self._stmt = self._stmt.order_by(col.asc())
        return self

    def _apply_delete_at_is_none(self) -> None:
        if deleted_column := self._model_cls.get_column_or_none(self._model_cls.deleted_at_column_name()):
            self._stmt = self._stmt.where(deleted_column.is_(None))


class QueryBuilder[T: ModelMixin](BaseBuilder[T]):
    def __init__(
        self,
        model_cls: type[T],
        *,
        session_provider: SessionProvider,
        initial_where: ColumnElement[bool] | None = None,
        custom_stmt: Select | None = None,
        include_deleted: bool | None = None,
    ):
        super().__init__(model_cls, session_provider=session_provider)

        self._stmt = custom_stmt if custom_stmt is not None else select(self._model_cls)

        if include_deleted is False and self._model_cls.has_deleted_at_column:
            self._apply_delete_at_is_none()

        if initial_where is not None:
            self._stmt = self._stmt.where(initial_where)

    @property
    def select_stmt(self) -> Select:
        return self._stmt

    def paginate(self, *, page: int, limit: int) -> Self:
        if not isinstance(page, int) or page < 1:
            raise ValueError("page must be greater than or equal to 1")

        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be greater than or equal to 1")

        self._stmt = self._stmt.offset((page - 1) * limit).limit(limit)
        return self

    async def all(self) -> list[T]:
        try:
            async with self._session_provider() as sess:
                result = await sess.execute(self._stmt)
                return result.scalars().all()
        except Exception as e:
            raise Exception(f"Error when querying all data, {self._model_cls.__name__}: {e}") from e

    async def first(self) -> T | None:
        try:
            async with self._session_provider() as sess:
                result = await sess.execute(self._stmt)
                return result.scalars().first()
        except Exception as e:
            raise Exception(f"Error when querying first data, {self._model_cls.__name__}: {e}") from e


class CountBuilder[T: ModelMixin](BaseBuilder[T]):
    def __init__(
        self,
        model_cls: type[T],
        *,
        session_provider: SessionProvider,
        count_column: InstrumentedAttribute = None,
        is_distinct: bool = False,
        include_deleted: bool = None,
    ):
        super().__init__(model_cls, session_provider=session_provider)
        col = count_column if count_column is not None else self._model_cls.id
        expr = func.count(distinct(col)) if is_distinct else func.count(col)
        self._stmt = select(expr)

        if include_deleted is False and self._model_cls.has_deleted_at_column():
            self._apply_delete_at_is_none()

    async def count(self) -> int:
        try:
            async with self._session_provider() as sess:
                return (await sess.execute(self._stmt)).scalar()
        except Exception as e:
            raise Exception(f"Error when querying count data, {self._model_cls.__name__}: {e}") from e


class UpdateBuilder[T: ModelMixin](BaseBuilder[T]):
    def __init__(
        self, *, model_cls: type[T] | None = None, model_ins: T | None = None, session_provider: SessionProvider
    ):
        target_cls = model_cls if model_cls is not None else model_ins.__class__
        super().__init__(target_cls, session_provider=session_provider)
        self._stmt = update(self._model_cls)
        self._update_dict = {}
        if model_ins is not None:
            self._stmt = self._stmt.where(self._model_cls.id == model_ins.id)

    def update(self, **kwargs) -> Self:
        for k, v in kwargs.items():
            if not self._model_cls.has_column(k):
                logger.warning(f"{k} is not a {self._model_cls.__name__} column")
                continue

            if isinstance(v, datetime) and v.tzinfo:
                v = v.replace(tzinfo=None)

            self._update_dict[k] = v
        return self

    def soft_delete(self) -> Self:
        if self._model_cls.has_deleted_at_column():
            self._update_dict[self._model_cls.deleted_at_column_name()] = utc_now_naive()
        return self

    @property
    def update_stmt(self) -> Update:
        if not self._update_dict:
            return self._stmt

        # 自动处理 updated_at 和 deleted_at 同步
        updated_col = self._model_cls.updated_at_column_name()
        deleted_col = self._model_cls.deleted_at_column_name()

        if deleted_col in self._update_dict:
            self._update_dict.setdefault(updated_col, self._update_dict[deleted_col])
        self._update_dict.setdefault(updated_col, utc_now_naive())

        if self._model_cls.has_updater_id_column():
            self._update_dict.setdefault(self._model_cls.updater_id_column_name(), async_context.get_user_id())

        return self._stmt.values(**self._update_dict).execution_options(synchronize_session=False)

    async def execute(self):
        if not self._update_dict:
            return
        try:
            async with self._session_provider() as sess:
                await sess.execute(self.update_stmt)
                await sess.commit()
        except Exception as e:
            raise Exception(f"Error when updating data, {self._model_cls.__name__}: {e}") from e
