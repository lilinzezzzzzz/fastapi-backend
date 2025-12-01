import uuid
from contextvars import ContextVar
from typing import Any, Dict

from pkg.logger_tool import logger

# --- 1. 核心 Context 定义 ---
_request_ctx_var: ContextVar[Dict[str, Any]] = ContextVar("request_ctx")


class _RequestContext:
    """
    请求上下文管理工具类
    """
    KEY_USER_ID = "user_id"
    KEY_TRACE_ID = "trace_id"

    @classmethod
    def init(cls, trace_id: str = None):
        """
        初始化上下文
        :return: 最终使用的 trace_id
        """
        # 优化：如果没传 trace_id，自动生成一个，保证系统健壮性
        final_trace_id = trace_id or str(uuid.uuid4())

        _request_ctx_var.set(
            {
                cls.KEY_TRACE_ID: final_trace_id,
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
    def all() -> Dict[str, Any]:
        try:
            return _request_ctx_var.get()
        except LookupError:
            return {}

    @staticmethod
    def clear():
        # 清理上下文
        _request_ctx_var.set({})


# 你的做法非常好：直接使用类作为单例入口
context = _RequestContext


# --- 2. 业务工具函数 (保持你的逻辑不变) ---

def set_user_id(user_id: int):
    context.set(context.KEY_USER_ID, user_id)


def get_user_id() -> int:
    user_id = context.get(context.KEY_USER_ID)
    if user_id is None:
        logger.warning("user_id is not set in current context")
        raise LookupError("user_id is not set")
    return user_id


def set_trace_id(trace_id: str):
    context.set(context.KEY_TRACE_ID, trace_id)


def get_trace_id() -> str:
    # 这里不需要 try-except LookupError 了，因为 context.get 内部处理了
    trace_id = context.get(context.KEY_TRACE_ID)

    if trace_id is None or trace_id == "unknown":
        raise LookupError("trace_id is unknown or not set")

    return trace_id
