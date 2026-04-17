"""异步 span 上下文与装饰器。"""

import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from functools import wraps
from inspect import iscoroutinefunction
from itertools import count
from typing import Any

from loguru import logger as loguru_logger


@dataclass(frozen=True, slots=True)
class SpanFrame:
    """当前活跃 span 的快照。"""

    span_seq: int
    span_name: str
    span_type: str
    span_depth: int
    span_path: str


class _SpanRuntime:
    """同一异步请求链内共享的 span 运行时。"""

    __slots__ = ("_seq_counter",)

    def __init__(self) -> None:
        self._seq_counter = count(1)

    def next_seq(self) -> int:
        return next(self._seq_counter)


_span_stack_var: ContextVar[tuple[SpanFrame, ...]] = ContextVar("logger_span_stack", default=())
_span_runtime_var: ContextVar[_SpanRuntime | None] = ContextVar("logger_span_runtime", default=None)


def _validate_required_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def get_current_span() -> SpanFrame | None:
    """返回当前活跃 span；如果不存在则返回 None。"""

    stack = _span_stack_var.get()
    if not stack:
        return None
    return stack[-1]


def get_span_record_extra() -> dict[str, Any]:
    """返回当前日志需要注入的 span 字段。"""

    frame = get_current_span()
    if frame is None:
        return {
            "span_seq": None,
            "span_name": None,
            "span_type": None,
            "span_depth": None,
            "span_path": None,
        }

    return {
        "span_seq": frame.span_seq,
        "span_name": frame.span_name,
        "span_type": frame.span_type,
        "span_depth": frame.span_depth,
        "span_path": frame.span_path,
    }


class _AsyncSpan:
    """仅支持 async with 的 span 上下文管理器。"""

    def __init__(self, *, name: str, span_type: str) -> None:
        self._name = _validate_required_text(name, field_name="name")
        self._span_type = _validate_required_text(span_type, field_name="span_type")
        self._frame: SpanFrame | None = None
        self._start_at: float | None = None
        self._stack_token: Token[tuple[SpanFrame, ...]] | None = None
        self._runtime_token: Token[_SpanRuntime | None] | None = None

    def __enter__(self) -> SpanFrame:
        raise TypeError("span_context() supports only 'async with' usage")

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> bool:
        raise TypeError("span_context() supports only 'async with' usage")

    async def __aenter__(self) -> SpanFrame:
        runtime = _span_runtime_var.get()
        if runtime is None:
            runtime = _SpanRuntime()
            self._runtime_token = _span_runtime_var.set(runtime)

        current_stack = _span_stack_var.get()
        span_seq = runtime.next_seq()
        span_depth = len(current_stack)
        path_segment = f"{span_seq}:{self._name}"
        span_path = f"{current_stack[-1].span_path}/{path_segment}" if current_stack else path_segment

        self._frame = SpanFrame(
            span_seq=span_seq,
            span_name=self._name,
            span_type=self._span_type,
            span_depth=span_depth,
            span_path=span_path,
        )
        self._stack_token = _span_stack_var.set((*current_stack, self._frame))
        self._start_at = time.perf_counter()

        loguru_logger.info("span.start")
        return self._frame

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool:
        elapsed_ms = 0.0
        if self._start_at is not None:
            elapsed_ms = round((time.perf_counter() - self._start_at) * 1000, 3)

        try:
            if exc is None:
                loguru_logger.bind(json_content={"elapsed_ms": elapsed_ms}).info("span.end")
            else:
                error_type = exc_type.__name__ if exc_type is not None else type(exc).__name__
                loguru_logger.bind(
                    json_content={
                        "elapsed_ms": elapsed_ms,
                        "error_type": error_type,
                    }
                ).error("span.error")
        finally:
            if self._stack_token is not None:
                _span_stack_var.reset(self._stack_token)
            if self._runtime_token is not None:
                _span_runtime_var.reset(self._runtime_token)

            self._frame = None
            self._start_at = None
            self._stack_token = None
            self._runtime_token = None

        return False


def span_context(name: str, *, span_type: str) -> _AsyncSpan:
    """创建异步 span 上下文。"""

    return _AsyncSpan(name=name, span_type=span_type)


def with_span[**P, T](
    *,
    span_type: str,
    name: str | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """为 async def 注入 span 上下文。"""

    validated_span_type = _validate_required_text(span_type, field_name="span_type")
    validated_name = None if name is None else _validate_required_text(name, field_name="name")

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        if not iscoroutinefunction(func):
            raise TypeError("with_span() supports async def only")

        span_name = validated_name or func.__qualname__

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            async with span_context(span_name, span_type=validated_span_type):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "SpanFrame",
    "get_current_span",
    "get_span_record_extra",
    "span_context",
    "with_span",
]
