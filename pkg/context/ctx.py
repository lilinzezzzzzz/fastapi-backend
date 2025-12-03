from pkg.context.manager import ctx_manager
from pkg.logger_tool import logger


# --- 2. 业务工具函数 (保持你的逻辑不变) ---

def set_user_id(user_id: int):
    ctx_manager.set("user_id", user_id)


def get_user_id() -> int:
    user_id = ctx_manager.get("user_id")
    if user_id is None:
        logger.warning("user_id is not set in current context")
        raise LookupError("user_id is not set")
    return user_id


def set_trace_id(trace_id: str):
    ctx_manager.set(ctx_manager.KEY_TRACE_ID, trace_id)


def get_trace_id() -> str:
    # 这里不需要 try-except LookupError 了，因为 context.get 内部处理了
    trace_id = ctx_manager.get(ctx_manager.KEY_TRACE_ID)

    if trace_id is None or trace_id == "unknown":
        raise LookupError("trace_id is unknown or not set")

    return trace_id
