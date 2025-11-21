from contextvars import ContextVar

from fastapi import Request

from pkg.logger_tool import logger


def set_user_id(request: Request, user_id: int):
    """
    设置用户ID
    :param request:
    :param user_id:
    :return:
    """
    request.state.user_id = user_id


def get_user_id(request: Request):
    """
    获取用户ID
    :param request:
    :return:
    """
    return request.state.user_id


trace_id_context_var: ContextVar[str] = ContextVar("trace_id", default="unknown")


def set_trace_id_context_var(trace_id: str):
    """设置 trace_id"""
    trace_id_context_var.set(trace_id)


def get_trace_id_context_var() -> str:
    """获取 trace_id，如果未设置，则返回 None"""
    try:
        trace_id = trace_id_context_var.get()
    except LookupError:
        raise

    if trace_id == "unknown":
        raise LookupError("trace_id is unknown")

    return trace_id


user_id_context_var: ContextVar[int] = ContextVar("user_id", default=-1)


def set_user_id_context_var(user_id: int):
    """设置当前请求的 user_id"""
    user_id_context_var.set(user_id)


def get_user_id_context_var() -> int:
    """获取当前请求的 user_id"""
    try:
        user_id = user_id_context_var.get()
    except LookupError:
        logger.warning("user_id is not set")
        raise

    # if user_id == -1:
    #     raise AppException(code=400, detail="user_id is unknown")

    return user_id