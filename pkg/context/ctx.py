from typing import Any

from pkg.context.base import ctx_manager
from pkg.logger_tool import logger


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
