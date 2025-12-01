import pytest
import asyncio
import sys
from unittest.mock import MagicMock

# --- Mock 依赖 ---
mock_logger = MagicMock()
sys.modules["pkg.logger_tool"] = MagicMock()
sys.modules["pkg.logger_tool"].logger = mock_logger

# --- 导入你的代码 ---
from pkg.context_tool import (
    context,
    set_user_id,
    get_user_id,
    get_trace_id,
)


# --- Fixture ---
@pytest.fixture(autouse=True)
def clean_context():
    context.clear()
    mock_logger.reset_mock()
    yield


# --- 测试用例 ---

def test_basic_lifecycle():
    """测试正常的生命周期"""
    tid = "trace-123"
    context.init(trace_id=tid)  # 正常传入

    assert get_trace_id() == tid

    set_user_id(1001)
    assert get_user_id() == 1001


def test_init_validation_error():
    """
    【修正后】测试必填参数校验
    需求：trace_id 为必须参数，不能为 None
    """
    # 验证：传入 None 应引发 ValueError
    with pytest.raises(ValueError, match="trace_id is mandatory"):
        context.init(trace_id=None)

    # 验证：传入空字符串 应引发 ValueError
    with pytest.raises(ValueError, match="trace_id is mandatory"):
        context.init(trace_id="")


def test_get_without_init():
    """测试没有 Init 时，Get 的行为"""
    # 业务函数 get_user_id 应该抛出异常
    with pytest.raises(LookupError, match="user_id is not set"):
        get_user_id()


def test_set_without_init_fallback():
    """测试没有 Init 时，Set 的防御性行为"""
    import pkg.context_tool
    from contextvars import ContextVar

    # 1. 保存旧的 ContextVar (避免影响其他测试)
    old_var = pkg.context_tool._request_ctx_var

    # 2. 【关键步骤】临时替换为一个全新的、未初始化的 ContextVar
    # 这样调用 get() 时一定会抛出 LookupError
    pkg.context_tool._request_ctx_var = ContextVar("temp_test_ctx")

    try:
        # 3. 执行测试：直接 Set
        # 此时 get() 会失败 -> 进入 except -> 初始化 dict -> 打印日志
        context.set("temp_key", "temp_value")

        # 验证值是否存进去了
        assert context.get("temp_key") == "temp_value"

        # 4. 验证日志是否被调用
        mock_logger.warning.assert_called_with("RequestContext used without initialization! Check Middleware.")

    finally:
        # 5. 【恢复现场】一定要把旧的变量还原回去，否则后续测试会挂
        pkg.context_tool._request_ctx_var = old_var


@pytest.mark.asyncio
async def test_async_context_isolation():
    """测试并发隔离性"""

    async def request_handler(trace_id, user_id, delay):
        context.init(trace_id=trace_id)  # 必须传入有效的 trace_id
        set_user_id(user_id)
        await asyncio.sleep(delay)
        return get_trace_id(), get_user_id()

    task_a = asyncio.create_task(request_handler("trace-A", 100, 0.1))
    task_b = asyncio.create_task(request_handler("trace-B", 200, 0.05))

    res_a = await task_a
    res_b = await task_b

    assert res_a == ("trace-A", 100)
    assert res_b == ("trace-B", 200)
