from contextvars import ContextVar
from typing import Any

from pkg.logger_tool import logger

_request_ctx_var: ContextVar[dict[str, Any]] = ContextVar("request_ctx")


class _RequestContext:
    """
    请求上下文管理工具类
    """
    KEY_TRACE_ID = "trace_id"

    @classmethod
    def init(cls, trace_id: str):
        """
        初始化上下文
        :return: 最终使用的 trace_id
        """
        # 优化：如果没传 trace_id，自动生成一个，保证系统健壮性
        if not trace_id:
            raise ValueError("trace_id is mandatory and cannot be empty or None")

        if not isinstance(trace_id, str):
            raise ValueError("trace_id must be a string")

        _request_ctx_var.set(
            {
                cls.KEY_TRACE_ID: trace_id,
            }
        )

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        try:
            ctx = _request_ctx_var.get()
        except LookupError:
            # 防御性编程：如果没有 init 就调用 get，返回 default 而不是报错
            return default

        return ctx.get(key, default)

    @staticmethod
    def set(key: str, value: Any):
        try:
            ctx = _request_ctx_var.get()
        except LookupError:
            # 严重错误：说明中间件没有运行！
            # 这种情况下，为了防止报错，可以初始化一个临时的（虽然这不应该发生）
            ctx = {}
            _request_ctx_var.set(ctx)
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


context = _RequestContext
