import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

from pkg.logger_tool import logger

# --- 1. 核心 Context 定义 ---

# 定义全局 ContextVar，存储一个字典
_request_ctx_var: ContextVar[Dict[str, Any]] = ContextVar("request_ctx", default={})


class RequestContext:
    """
    请求上下文管理工具类 (统一管理入口)
    """

    # 定义常用的 Key 常量，避免魔法字符串
    KEY_USER_ID = "user_id"
    KEY_TRACE_ID = "trace_id"

    @staticmethod
    def init(trace_id: str = None) -> str:
        """
        初始化当前请求的上下文。
        通常在 Middleware 中调用。
        """
        ctx = {
            RequestContext.KEY_TRACE_ID: trace_id,
        }
        _request_ctx_var.set(ctx)
        return trace_id

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        ctx = _request_ctx_var.get()
        return ctx.get(key, default)

    @staticmethod
    def set(key: str, value: Any):
        ctx = _request_ctx_var.get()
        ctx[key] = value

    @staticmethod
    def all() -> Dict[str, Any]:
        return _request_ctx_var.get()

    @staticmethod
    def clear():
        _request_ctx_var.set({})


# 方便导入的单例对象
context = RequestContext()


# --- 2. 重构后的业务工具函数 ---
# 注意：这些函数不再需要接收 request 对象

def set_user_id(user_id: int):
    """
    设置当前上下文的用户ID
    (替代了原有的 request.state.user_id 和 set_user_id_context_var)
    """
    RequestContext.set(RequestContext.KEY_USER_ID, user_id)


def get_user_id() -> int:
    """
    获取当前上下文的用户ID
    """
    user_id = RequestContext.get(RequestContext.KEY_USER_ID)

    # 保持原有逻辑：如果没获取到，打印警告并抛出异常
    if user_id is None:
        logger.warning("user_id is not set in current context")
        # 视业务需求，这里可以抛出异常，或者返回 None/-1
        # 为了兼容原有 get_user_id_context_var 的严格行为，这里抛错
        raise LookupError("user_id is not set")

    return user_id


def set_trace_id(trace_id: str):
    """设置 trace_id"""
    RequestContext.set(RequestContext.KEY_TRACE_ID, trace_id)


def get_trace_id() -> str:
    """获取 trace_id"""
    trace_id = RequestContext.get(RequestContext.KEY_TRACE_ID)

    if trace_id is None or trace_id == "unknown":
        raise LookupError("trace_id is unknown or not set")

    return trace_id
