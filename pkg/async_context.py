from contextvars import ContextVar
from typing import Any

from pkg.async_logger import logger

_request_context_var: ContextVar[dict[str, Any]] = ContextVar("request_context")


class _RequestContextManager:
    """
    请求上下文管理工具类
    """

    @staticmethod
    def init(**kwargs) -> dict[str, Any]:
        """
        初始化上下文，必须在中间件开始时调用
        """
        ctx = {
            **kwargs,
        }
        _request_context_var.set(ctx)
        return ctx

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        try:
            ctx = _request_context_var.get()
            return ctx.get(key, default)
        except LookupError:
            # 如果没有 init，返回 default，兼容非 Web 环境调用
            return default

    @staticmethod
    def set(key: str, value: Any):
        try:
            ctx = _request_context_var.get()
            ctx[key] = value
        except LookupError as e:
            # 修改：移除自动 init，直接报错或记录严重错误
            # 如果这是一个纯 Web 包，应该 raise 异常。
            # 如果为了兼容，打印 Error 且不执行操作可能更安全。
            logger.error(f"Try to set context key '{key}' but Context is not initialized!")
            raise RuntimeError("Request Context not initialized. Is Middleware added?") from e

    @staticmethod
    def all() -> dict[str, Any]:
        try:
            return _request_context_var.get()
        except LookupError:
            return {}

    @staticmethod
    def clear():
        try:
            _request_context_var.get().clear()
        except LookupError:
            pass  # 未初始化时无需清理


_ctx_manager = _RequestContextManager()


def init(**kwargs) -> dict[str, Any]:
    ctx = _ctx_manager.init(**kwargs)
    return ctx


def clear():
    _ctx_manager.clear()


def set_val(key: str, value: Any):
    _ctx_manager.set(key, value)


def get_val(key: str, default: Any = None):
    return _ctx_manager.get(key, default)


def set_user_id(user_id: int):
    _ctx_manager.set("user_id", user_id)


def get_user_id() -> int:
    user_id = _ctx_manager.get("user_id")
    if user_id is None:
        logger.warning("user_id is not set in current context")
        raise LookupError("user_id is not set")
    return user_id


def set_trace_id(trace_id: str):
    if not trace_id:
        raise ValueError("trace_id is mandatory and cannot be empty or None")

    if not isinstance(trace_id, str):
        raise ValueError("trace_id must be a string")

    _ctx_manager.set("trace_id", trace_id)


def get_trace_id() -> str:
    # 这里不需要 try-except LookupError 了，因为 context.get 内部处理了
    trace_id = _ctx_manager.get("trace_id")

    if trace_id is None or trace_id == "unknown":
        raise LookupError("trace_id is unknown or not set")

    return trace_id
