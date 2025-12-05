import sys
import time
import os
import threading
from typing import Any

import pytest
import anyio
from unittest.mock import MagicMock

# --- 1. Mock 外部依赖 (必须在导入 pkg.anyio_task 之前) ---
mock_logger = MagicMock()
sys.modules["pkg.logger_tool"] = MagicMock()
sys.modules["pkg.logger_tool"].logger = mock_logger

# --- 2. 导入待测模块 ---
from pkg.anyio_task import AnyioTaskHandler


# --- 3. 定义顶层 helper 函数 ---

async def async_job(duration: float, result: str):
    await anyio.sleep(duration)
    return result


async def async_job_error():
    await anyio.sleep(0.1)
    raise ValueError("Test Error")


def sync_job(duration: float, result: str):
    time.sleep(duration)
    return result


def sync_cpu_job(x: int, y: int):
    return x + y


def get_thread_id():
    return threading.get_ident()


def get_process_id():
    return os.getpid()


# --- 4. Pytest Fixtures ---

@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
async def manager():
    mgr = AnyioTaskHandler()
    mgr.max_queue = 100
    await mgr.start()
    yield mgr
    await mgr.shutdown()


# --- 5. 测试用例 ---

@pytest.mark.anyio
class TestAnyioTaskManager:

    # 1. 测试 add_task
    async def test_add_task_success(self, manager):
        result_box: dict[str, Any] = {"value": None}

        async def side_effect_job():
            await anyio.sleep(0.1)
            result_box["value"] = "done"

        await manager.add_task("task_1", coro_func=side_effect_job)

        status = await manager.get_task_status()
        assert "task_1" in status
        assert status["task_1"] is True

        # 使用轮询等待任务清理，比固定 sleep 更稳定
        for _ in range(20):
            status = await manager.get_task_status()
            if "task_1" not in status:
                break
            await anyio.sleep(0.05)

        assert result_box["value"] == "done"
        assert "task_1" not in status

    # 2. 测试 add_task 的去重逻辑
    async def test_add_task_duplicate(self, manager):
        async def long_job():
            await anyio.sleep(1)

        success1 = await manager.add_task("dup_task", coro_func=long_job)
        success2 = await manager.add_task("dup_task", coro_func=long_job)

        assert success1 is True
        assert success2 is False

    # 3. 测试 add_task 超时
    async def test_add_task_timeout(self, manager):
        mock_logger.reset_mock()
        await manager.add_task("timeout_task", coro_func=async_job, args_tuple=(1.0, "res"), timeout=0.1)

        # 等待日志出现
        for _ in range(10):
            if mock_logger.error.called or mock_logger.info.called:
                break
            await anyio.sleep(0.05)

        assert mock_logger.error.called or mock_logger.info.called

    # 4. [修复] 测试 cancel_task
    async def test_cancel_task(self, manager):
        async def forever_job():
            await anyio.sleep(10)

        await manager.add_task("cancel_me", coro_func=forever_job)
        await anyio.sleep(0.01)

        cancel_success = await manager.cancel_task("cancel_me")
        assert cancel_success is True

        # [关键修复] 轮询等待 cleanup 完成
        # 任务被取消后，更新状态到从字典移除中间有微小的延迟
        task_removed = False
        for _ in range(20):  # 最多等 1秒
            status = await manager.get_task_status()
            # 只要 key 不在了，说明清理完毕
            if "cancel_me" not in status:
                task_removed = True
                break
            # 如果 key 还在，但 value 是 False，说明处于中间态，继续等
            await anyio.sleep(0.05)

        assert task_removed is True, "Task 'cancel_me' should be removed from tasks list"

    # 5. 测试 run_gather_with_concurrency
    async def test_gather_concurrency_success(self, manager):
        args = [(0.1, 1), (0.1, 2), (0.1, 3)]
        results = await manager.run_gather_with_concurrency(
            async_job,
            args,
            jitter=0
        )
        assert results == [1, 2, 3]

    async def test_gather_concurrency_partial_timeout(self, manager):
        args = [(0.1, "fast"), (1.0, "slow")]
        results = await manager.run_gather_with_concurrency(
            async_job,
            args,
            task_timeout=0.2,
            jitter=0
        )
        assert results[0] == "fast"
        assert results[1] is None

    async def test_gather_concurrency_global_timeout(self, manager):
        args = [(0.5, "A"), (0.5, "B")]
        results = await manager.run_gather_with_concurrency(
            async_job,
            args,
            global_timeout=0.2,
            jitter=0
        )
        assert results == [None, None]

    # 6. 测试 run_in_thread
    async def test_run_in_thread(self, manager):
        start_time = time.time()
        res = await manager.run_in_thread(sync_job, args_tuple=(0.2, "thread_res"))
        end_time = time.time()

        assert res == "thread_res"
        assert end_time - start_time >= 0.2

        main_thread = threading.get_ident()
        worker_thread = await manager.run_in_thread(get_thread_id)
        assert main_thread != worker_thread

    # 7. 测试 run_in_process
    async def test_run_in_process(self, manager):
        res = await manager.run_in_process(sync_cpu_job, args_tuple=(5, 10))
        assert res == 15

        main_pid = os.getpid()
        worker_pid = await manager.run_in_process(get_process_id)
        assert main_pid != worker_pid

    # 8. 测试 run_in_threads
    async def test_run_in_threads_batch(self, manager):
        args_list = [(0.1, "t1"), (0.1, "t2")]
        results = await manager.run_in_threads(sync_job, args_tuple_list=args_list)
        assert results == ["t1", "t2"]

    # 9. 测试 run_in_processes
    async def test_run_in_processes_batch(self, manager):
        args_list = [(1, 1), (2, 2)]
        results = await manager.run_in_processes(sync_cpu_job, args_tuple_list=args_list)
        assert results == [2, 4]

    # 10. 测试异常处理
    async def test_task_internal_exception(self, manager):
        mock_logger.reset_mock()
        await manager.add_task("error_task", coro_func=async_job_error)

        for _ in range(10):
            if mock_logger.error.called:
                break
            await anyio.sleep(0.05)

        assert mock_logger.error.called

    # 11. 测试 Shutdown
    async def test_shutdown_with_running_tasks(self, manager):
        async def slow_task():
            try:
                await anyio.sleep(2)
            except anyio.get_cancelled_exc_class():
                pass

        await manager.add_task("closing_task", coro_func=slow_task)

        start_shutdown = time.time()
        await manager.shutdown()
        end_shutdown = time.time()

        assert end_shutdown - start_shutdown < 2.0
