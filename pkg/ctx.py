from contextvars import ContextVar
from typing import Any

from pkg.logger_tool import logger

_request_ctx_var: ContextVar[dict[str, Any]] = ContextVar("request_ctx")


class _RequestCtxManager:
    """
    请求上下文管理工具类
    """

    @classmethod
    def init(cls) -> dict[str, Any]:
        """
        初始化上下文
        :return: 最终使用的 trace_id
        """
        # 优化：如果没传 trace_id，自动生成一个，保证系统健壮性
        ctx = {}
        _request_ctx_var.set(ctx)
        return ctx

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        try:
            ctx = _request_ctx_var.get()
        except LookupError:
            # 防御性编程：如果没有 init 就调用 get，返回 default 而不是报错
            return default

        return ctx.get(key, default)

    @classmethod
    def set(cls, key: str, value: Any):
        try:
            ctx = _request_ctx_var.get()
        except LookupError:
            # 严重错误：说明中间件没有运行！
            # 这种情况下，为了防止报错，可以初始化一个临时的（虽然这不应该发生）
            ctx = cls.init()
            logger.warning("RequestContext used without initialization! Check Middleware.")

        ctx[key] = value

    @staticmethod
    def all() -> dict[str, Any]:
        try:
            return _request_ctx_var.get()
        except LookupError:
            return {}

    @staticmethod
    def clear():
        # 清理上下文
        _request_ctx_var.set({})


ctx_manager = _RequestCtxManager


def init():
    ctx = ctx_manager.init()
    return ctx


def set_val(key: str, value: Any):
    ctx_manager.set(key, value)


def get_val(key: str):
    return ctx_manager.get(key)


def set_user_id(user_id: int):
    ctx_manager.set("user_id", user_id)


def get_user_id() -> int:
    user_id = ctx_manager.get("user_id")
    if user_id is None:
        logger.warning("user_id is not set in current context")
        raise LookupError("user_id is not set")
    return user_id


def set_trace_id(trace_id: str):
    if not trace_id:
        raise ValueError("trace_id is mandatory and cannot be empty or None")

    if not isinstance(trace_id, str):
        raise ValueError("trace_id must be a string")

    ctx_manager.set("trace_id", trace_id)


def get_trace_id() -> str:
    # 这里不需要 try-except LookupError 了，因为 context.get 内部处理了
    trace_id = ctx_manager.get("trace_id")

    if trace_id is None or trace_id == "unknown":
        raise LookupError("trace_id is unknown or not set")

    return trace_id
