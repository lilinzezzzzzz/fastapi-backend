from datetime import datetime
from typing import Any, cast

from sqlalchemy import (Column, ColumnExpressionArgument, Delete, Function, Select, Subquery, Update,
                        distinct, func, or_, select, update)
from sqlalchemy.orm import InstrumentedAttribute, aliased
from sqlalchemy.sql.elements import ClauseElement, ColumnElement

from pkg.context import ctx
from pkg.orm.model_mixin import ModelMixin
from pkg import get_utc_without_tzinfo, unique_list
from pkg.logger_tool import logger
from pkg.orm.base import SessionProvider


class BaseBuilder[T: ModelMixin]:
    """SQL查询构建器基类，提供模型类和方法的基本结构"""

    __slots__ = ("_model_cls", "_stmt", "_session_provider")

    def __init__(
            self,
            model_cls: type[T],  # 这里直接使用 T
            *,
            session_provider: SessionProvider
    ):
        if not isinstance(model_cls, type) or not issubclass(model_cls, ModelMixin):
            raise Exception(f"model_class must be a subclass of ModelMixin, and actually gets: {type(model_cls)}")

        self._model_cls: type[T] = model_cls
        self._stmt: Select | Delete | Update | None = None
        self._session_provider = session_provider

    def eq_(self, column: InstrumentedAttribute, value: Any) -> "BaseBuilder[T]":
        return self.where(column == value)

    def ne_(self, column: InstrumentedAttribute, value: Any) -> "BaseBuilder[T]":
        return self.where(column != value)

    def gt_(self, column: InstrumentedAttribute, value: Any) -> "BaseBuilder[T]":
        return self.where(column > value)

    def lt_(self, column: InstrumentedAttribute, value: Any) -> "BaseBuilder[T]":
        return self.where(column < value)

    def ge_(self, column: InstrumentedAttribute, value: Any) -> "BaseBuilder[T]":
        return self.where(column >= value)

    def le_(self, column: InstrumentedAttribute, value: Any) -> "BaseBuilder[T]":
        return self.where(column <= value)

    def in_(self, column: InstrumentedAttribute, values: list | tuple) -> "BaseBuilder[T]":
        if not isinstance(values, (list, tuple)):
            raise TypeError("values must be a list or tuple")
        unique_values = unique_list(values, exclude_none=True)
        if len(unique_values) == 1:
            return self.where(column == unique_values[0])
        return self.where(column.in_(unique_values))

    def not_in_(self, column: InstrumentedAttribute, values: list | tuple) -> "BaseBuilder[T]":
        if not isinstance(values, (list, tuple)):
            raise TypeError("values must be a list or tuple")
        unique_values = unique_list(values, exclude_none=True)
        if len(unique_values) == 1:
            return self.where(column != unique_values[0])
        return self.where(column.notin_(unique_values))

    def like(self, column: InstrumentedAttribute, pattern: str) -> "BaseBuilder[T]":
        return self.where(column.like(f"%{pattern}%"))

    def ilike(self, column: InstrumentedAttribute, pattern: str) -> "BaseBuilder[T]":
        return self.where(column.ilike(f"%{pattern}%"))

    def is_null(self, column: InstrumentedAttribute) -> "BaseBuilder[T]":
        return self.where(column.is_(None))

    def is_not_null(self, column: InstrumentedAttribute) -> "BaseBuilder[T]":
        return self.where(column.isnot(None))

    def between_(self, column: InstrumentedAttribute, start_value: Any, end_value: Any) -> "BaseBuilder[T]":
        return self.where(column.between(start_value, end_value))

    def contains_(self, column: InstrumentedAttribute, values: list | tuple) -> "BaseBuilder[T]":
        if not isinstance(values, (list, tuple)):
            raise TypeError("values must be a list or tuple")
        unique_values = unique_list(values, exclude_none=True)
        return self.where(column.contains(unique_values))

    def or_(self, *conditions: ColumnElement[bool]) -> "BaseBuilder[T]":
        if not conditions:
            return self
        self._stmt = self._stmt.where(or_(*conditions))
        return self

    def distinct_(self, *cols: InstrumentedAttribute) -> "BaseBuilder[T]":
        self._stmt = self._stmt.distinct(*cols)
        return self

    def group_by_(self, *cols: InstrumentedAttribute) -> "BaseBuilder[T]":
        if not cols:
            return self
        self._stmt = self._stmt.group_by(*cols)
        return self

    def desc_(self, col: InstrumentedAttribute) -> "BaseBuilder[T]":
        self._stmt = self._stmt.order_by(col.desc())
        return self

    def asc_(self, col: InstrumentedAttribute) -> "BaseBuilder[T]":
        self._stmt = self._stmt.order_by(col.asc())
        return self

    def _apply_delete_at_is_none(self) -> None:
        deleted_column = self._model_cls.get_column_or_none(self._model_cls.deleted_at_column_name())
        self._stmt = self._stmt.where(deleted_column.is_(None))

    def where(self, *conditions: ClauseElement) -> "BaseBuilder[T]":
        if not conditions:
            return self
        self._stmt = self._stmt.where(*conditions)
        return self


# 继承时显式传递泛型参数 [T]
class QueryBuilder[T: ModelMixin](BaseBuilder[T]):

    def __init__(
            self,
            model_cls: type[T],
            *,
            initial_where: ColumnExpressionArgument | None = None,
            custom_stmt: Select | None = None,
            session_provider: SessionProvider,
            include_deleted: bool | None = None
    ):
        super().__init__(model_cls=model_cls, session_provider=session_provider)

        if custom_stmt is not None:
            self._stmt: Select = custom_stmt
        else:
            self._stmt: Select = select(self._model_cls)
            if include_deleted is False and self._model_cls.has_deleted_at_column:
                self._apply_delete_at_is_none()
            if initial_where is not None:
                self._stmt = self._stmt.where(initial_where)

    @property
    def select_stmt(self) -> Select:
        return self._stmt

    @property
    def subquery_stmt(self) -> Subquery:
        return self._stmt.subquery()

    # 返回类型明确为 list[T]
    async def all(self, *, include_deleted: bool | None = None) -> list[T]:
        if include_deleted is False and self._model_cls.has_deleted_at_column:
            self._apply_delete_at_is_none()

        async with self._session_provider() as sess:
            try:
                result = await sess.execute(self._stmt)
                raw_data = result.scalars().all()
                # 使用 cast 强转类型，这里直接用 T
                data = cast(list[T], raw_data)
            except Exception as e:
                raise Exception(f"{self._model_cls.__name__} get all error: {e}")
        return data

    # 返回类型明确为 T | None
    async def first(self, *, include_deleted: bool | None = None) -> T | None:
        if include_deleted is False and self._model_cls.has_deleted_at_column:
            self._apply_delete_at_is_none()

        async with self._session_provider() as sess:
            try:
                result = await sess.execute(self._stmt)
                raw_data = result.scalars().first()
                data = cast(T | None, raw_data)
            except Exception as e:
                raise Exception(f"{self._model_cls.__name__} get first error: {e}")
        return data

    def paginate(self, *, page: int | None = None, limit: int | None = None) -> "QueryBuilder[T]":
        if page and limit:
            self._stmt = self._stmt.offset((page - 1) * limit).limit(limit)
        return self

    def limit(self, limit: int) -> "QueryBuilder[T]":
        self._stmt = self._stmt.limit(limit)
        return self


class CountBuilder[T: ModelMixin](BaseBuilder[T]):
    def __init__(
            self,
            model_cls: type[T],
            *,
            count_column: InstrumentedAttribute = None,
            is_distinct: bool = False,
            session_provider: SessionProvider,
            include_deleted: bool = None
    ):
        super().__init__(model_cls, session_provider=session_provider)

        count_column: InstrumentedAttribute = count_column if count_column is not None else self._model_cls.id

        if is_distinct:
            expression: Function[Column] = func.count(distinct(count_column))
        else:
            expression: Function[Column] = func.count(count_column)

        self._stmt: Select = select(expression)

        if include_deleted is False and self._model_cls.has_deleted_at_column():
            self._apply_delete_at_is_none()

    @property
    def count_stmt(self) -> Select:
        return self._stmt

    async def count(self) -> int:
        async with self._session_provider() as sess:
            try:
                exec_result = await sess.execute(self._stmt)
                data = exec_result.scalar()
            except Exception as e:
                raise Exception(f"{self._model_cls.__name__} count error: {e}")
        return data


class UpdateBuilder[T: ModelMixin](BaseBuilder[T]):
    def __init__(
            self,
            *,
            model_cls: type[T] | None = None,
            model_ins: T | None = None,
            session_provider: SessionProvider
    ):
        if (model_cls is None) == (model_ins is None):
            raise Exception("must and can only provide one of model_class or model_instance")

        # 如果传的是实例，取其类
        target_cls = model_cls if model_cls is not None else model_ins.__class__

        super().__init__(target_cls, session_provider=session_provider)

        self._stmt: Update = update(self._model_cls)
        self._update_dict = {}

        if model_ins is not None:
            model_id_column: InstrumentedAttribute = self._model_cls.get_column_or_none("id")
            self._stmt = self._stmt.where(model_id_column == model_ins.id)

    def update(self, **kwargs) -> "UpdateBuilder[T]":
        if not kwargs:
            return self

        for column_name, value in kwargs.items():
            if not self._model_cls.has_column(column_name):
                continue

            if isinstance(value, datetime) and value.tzinfo is not None:
                value = value.replace(tzinfo=None)

            self._update_dict[column_name] = value

        return self

    def soft_delete(self) -> "UpdateBuilder[T]":
        if not self._model_cls.has_deleted_at_column():
            return self

        self._update_dict[self._model_cls.deleted_at_column_name()] = get_utc_without_tzinfo()
        return self

    @property
    def update_stmt(self) -> Update:
        if not self._update_dict:
            return self._stmt

        current_time = get_utc_without_tzinfo()
        updated_at_column_name = self._model_cls.updated_at_column_name()

        if (deleted_at_column_name := self._model_cls.deleted_at_column_name()) in self._update_dict:
            self._update_dict.setdefault(
                updated_at_column_name,
                self._update_dict[deleted_at_column_name]
            )

        self._update_dict.setdefault(updated_at_column_name, current_time)

        user_id = ctx.get_user_id()
        if self._model_cls.has_updater_id_column():
            self._update_dict.setdefault(
                self._model_cls.updater_id_column_name(),
                user_id
            )

        self._stmt = self._stmt.values(**self._update_dict).execution_options(synchronize_session=False)

        return self._stmt

    async def execute(self):
        if not self._update_dict:
            logger.warning(f"{self._model_cls.__name__} no update data")
            return

        async with self._session_provider() as sess:
            try:
                await sess.execute(self.update_stmt)
                await sess.commit()
            except Exception as e:
                raise Exception(f"{self._model_cls.__name__} execute update_stmt failed: {e}")


def _validate_model_cls(model_cls: type, expected_type: type = type, subclass_of: type = ModelMixin):
    if model_cls is None:
        raise Exception("model_cls cannot be None")
    if not isinstance(model_cls, expected_type):
        raise Exception(f"model_cls must be a {expected_type.__name__}, got {type(model_cls).__name__}")
    if not issubclass(model_cls, subclass_of):
        raise Exception(f"model_cls must be a subclass of {subclass_of.__name__}, got {model_cls.__name__}")


def _validate_model_ins(model_ins: object, expected_type: type = ModelMixin):
    if model_ins is None:
        raise Exception("model_ins cannot be None")
    if not isinstance(model_ins, expected_type):
        raise Exception(f"model_ins must be a {expected_type.__name__} instance, got {type(model_ins).__name__}")


# -------------------------------------------------------------------------
# 工厂函数也使用 Python 3.12 泛型语法 [T: ModelMixin]
# 这样调用 new_cls_querier(User, ...) 时，返回类型会被推断为 QueryBuilder[User]
# -------------------------------------------------------------------------

def new_cls_querier[T: ModelMixin](
        model_cls: type[T],
        *,
        initial_where: ColumnExpressionArgument | None = None,
        session_provider: SessionProvider,
        include_deleted: bool | None = None
) -> QueryBuilder[T]:
    """创建一个新的查询器实例"""
    _validate_model_cls(model_cls)
    return QueryBuilder(
        model_cls=model_cls,
        initial_where=initial_where,
        session_provider=session_provider,
        include_deleted=include_deleted
    )


def new_sub_querier[T: ModelMixin](
        model_cls: type[T],
        *,
        subquery: Subquery,
        initial_where: ColumnExpressionArgument | None = None,
        session_provider: SessionProvider,
        include_deleted: bool | None = None
) -> QueryBuilder[T]:
    """创建一个新的子查询器实例"""
    _validate_model_cls(model_cls)
    alias = aliased(model_cls, subquery)
    return QueryBuilder(
        model_cls=model_cls,
        initial_where=initial_where,
        custom_stmt=select(alias),
        session_provider=session_provider,
        include_deleted=include_deleted
    )


def new_custom_querier[T: ModelMixin](
        model_cls: type[T],
        *,
        custom_stmt: Select,
        initial_where: ColumnExpressionArgument | None = None,
        session_provider: SessionProvider,
        include_deleted: bool | None = None,
) -> QueryBuilder[T]:
    """创建一个新的自定义查询器实例"""
    _validate_model_cls(model_cls)
    return QueryBuilder(
        model_cls=model_cls,
        include_deleted=include_deleted,
        initial_where=initial_where,
        custom_stmt=custom_stmt,
        session_provider=session_provider
    )


def new_cls_updater[T: ModelMixin](
        model_cls: type[T],
        *,
        session_provider: SessionProvider
) -> UpdateBuilder[T]:
    """创建一个基于模型类的更新器"""
    _validate_model_cls(model_cls)
    return UpdateBuilder(model_cls=model_cls, session_provider=session_provider)


def new_ins_updater[T: ModelMixin](
        model_ins: T,
        *,
        session_provider: SessionProvider
) -> UpdateBuilder[T]:
    """创建一个基于模型实例的更新器"""
    _validate_model_ins(model_ins)
    return UpdateBuilder(model_ins=model_ins, session_provider=session_provider)


def new_counter[T: ModelMixin](
        model_cls: type[T],
        *,
        session_provider: SessionProvider,
        include_deleted: bool | None = None
) -> CountBuilder[T]:
    """创建一个新的计数器实例"""
    _validate_model_cls(model_cls)
    return CountBuilder(model_cls=model_cls, session_provider=session_provider, include_deleted=include_deleted)


def new_col_counter[T: ModelMixin](
        model_cls: type[T],
        *,
        count_column: InstrumentedAttribute,
        is_distinct: bool = False,
        session_provider: SessionProvider,
        include_deleted: bool | None = None
) -> CountBuilder[T]:
    """创建一个新的计数器实例，针对特定的列"""
    _validate_model_cls(model_cls)
    return CountBuilder(
        model_cls=model_cls,
        count_column=count_column,
        session_provider=session_provider,
        include_deleted=include_deleted,
        is_distinct=is_distinct
    )
