import multiprocessing
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal

import anyio
from anyio import (
    CancelScope,
    CapacityLimiter,
    create_task_group,
    fail_after,
    to_process,
    to_thread,
    move_on_after,
    get_cancelled_exc_class,
)
from anyio.abc import TaskGroup

from pkg.logger_tool import logger

CPU = max(1, multiprocessing.cpu_count())
# 稍微调整参数逻辑，确保合理
GLOBAL_MAX_DEFAULT = min(max(32, 4 * CPU), 256)
THREAD_MAX_DEFAULT = min(max(16, (2 * GLOBAL_MAX_DEFAULT) // 3), 128)
PROCESS_MAX_DEFAULT = max(1, min(CPU, 8))

DEFAULT_TIMEOUT = 180
ANYIO_TM_MAX_QUEUE = 10_000


@dataclass
class TaskInfo:
    task_id: str
    name: str
    scope: CancelScope
    status: str = "running"  # running | completed | failed | cancelled | timeout
    result: Any = None
    exception: BaseException | None = None


class AnyioTaskManager:
    def __init__(self):
        self._global_limiter = CapacityLimiter(GLOBAL_MAX_DEFAULT)
        self._thread_limiter = CapacityLimiter(THREAD_MAX_DEFAULT)
        self._process_limiter = CapacityLimiter(PROCESS_MAX_DEFAULT)

        self._tg: TaskGroup | None = None
        self._tg_started = False
        self._lock = anyio.Lock()
        self.tasks: dict[str, TaskInfo] = {}
        self.max_queue = ANYIO_TM_MAX_QUEUE
        self.default_timeout = DEFAULT_TIMEOUT

    # ---------- lifecycle ----------
    async def start(self):
        if self._tg_started:
            return
        # 创建持久运行的 TaskGroup
        self._tg = await create_task_group().__aenter__()
        self._tg_started = True
        logger.info("AsyncTaskManagerAnyIO started.")

    async def shutdown(self):
        logger.info("Shutting down AsyncTaskManagerAnyIO...")
        async with self._lock:
            # fix: 使用 list() 创建快照，防止遍历时字典大小因任务完成而改变
            active_tasks = list(self.tasks.values())
            for info in active_tasks:
                try:
                    info.scope.cancel()
                except Exception as e:
                    logger.warning(f"Error canceling task {info.task_id}: {e}")

        if self._tg_started and self._tg is not None:
            try:
                # 退出 TaskGroup 会等待所有任务取消完成
                await self._tg.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error closing TaskGroup: {e}")
            finally:
                self._tg = None
                self._tg_started = False
        logger.info("AsyncTaskManagerAnyIO stopped.")

    # ---------- helpers ----------
    @staticmethod
    def get_coro_func_name(func: Callable[..., Any]) -> str:
        if getattr(func, "__name__", None) == "<lambda>":
            # 如果确实需要支持 lambda，可以返回 "lambda:<id>"，但通常不建议
            return "lambda_func"

        # 递归解包 partial
        while isinstance(func, partial):
            func = func.func

        if hasattr(func, "__self__"):
            return f"{func.__self__.__class__.__name__}.{func.__name__}"
        if hasattr(func, "__name__"):
            return func.__name__
        return str(func)

    async def _run_task_inner(
            self,
            info: TaskInfo,
            coro_func: Callable[..., Awaitable[Any]],
            args_tuple: tuple,
            kwargs_dict: dict,
            timeout: float | None,
    ):
        coro_name = info.name
        task_id = info.task_id

        try:
            async with self._global_limiter:
                logger.info(f"Task {coro_name} [{task_id}] started.")

                # 统一超时逻辑
                if timeout and timeout > 0:
                    with fail_after(timeout):
                        result = await coro_func(*args_tuple, **kwargs_dict)
                else:
                    result = await coro_func(*args_tuple, **kwargs_dict)

                info.status = "completed"
                info.result = result
                logger.info(f"Task {coro_name} [{task_id}] completed.")

        except TimeoutError as te:
            info.status = "timeout"
            info.exception = te
            logger.error(f"Task {coro_name} [{task_id}] timed out after {timeout}s.")
        except get_cancelled_exc_class():
            info.status = "cancelled"
            logger.info(f"Task {coro_name} [{task_id}] cancelled.")
            # 必须重新抛出 CancelledError 以便 anyio 正确处理取消传播，
            # 但这里我们是在 fire-and-forget 的顶层包装里，可以吞掉它，
            # 只要确保 info 状态更新即可。
        except BaseException as e:
            info.status = "failed"
            info.exception = e
            logger.error(f"Task {coro_name} [{task_id}] failed, err={e}", exc_info=True)
        finally:
            # 安全移除任务
            async with self._lock:
                self.tasks.pop(task_id, None)

    async def _execute_sync(
            self,
            sync_func: Callable,
            args: tuple,
            kwargs: dict,
            timeout: float | None,
            cancellable: bool,
            backend: Literal["thread", "process"]
    ) -> Any:
        """内部通用方法：执行单个同步任务"""
        func_name = self.get_coro_func_name(sync_func)

        logger.info(f"Task {func_name} started in {backend}.")
        bound = partial(sync_func, *args, **kwargs)

        # 定义内部执行函数，显式区分后端以满足类型检查
        async def _run():
            if backend == "thread":
                return await to_thread.run_sync(
                    bound, cancellable=cancellable, limiter=self._thread_limiter
                )
            else:
                return await to_process.run_sync(
                    bound, cancellable=cancellable, limiter=self._process_limiter
                )

        if timeout and timeout > 0:
            with fail_after(timeout):
                return await _run()
        return await _run()
    # ---------- public APIs ----------
    async def add_task(
            self,
            task_id: str | int,
            *,
            coro_func: Callable[..., Awaitable[Any]],
            args_tuple: tuple = (),
            kwargs_dict: dict | None = None,
            timeout: float | None = None,
    ) -> bool:
        if not self._tg_started or self._tg is None:
            raise RuntimeError("AsyncTaskManagerAnyIO is not started. Call await start() first.")

        task_id = str(task_id)
        kwargs_dict = kwargs_dict or {}
        coro_name = self.get_coro_func_name(coro_func)

        async with self._lock:
            if len(self.tasks) >= self.max_queue:
                logger.error(f"Queue overflow: {len(self.tasks)}/{self.max_queue}")
                raise Exception(f"Queue overflow: {self.max_queue}")

            if task_id in self.tasks:
                logger.warning(f"Task {task_id} already exists.")
                return False

            scope = CancelScope()
            info = TaskInfo(task_id=task_id, name=coro_name, scope=scope)
            self.tasks[task_id] = info

            # 使用 start_soon 提交到 TaskGroup
            self._tg.start_soon(
                self._run_task_inner, info, coro_func, args_tuple, kwargs_dict, timeout
            )
        return True

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            info = self.tasks.get(task_id)
            if info:
                info.scope.cancel()
                logger.info(f"Triggered cancellation for Task {task_id}.")
                return True
            logger.warning(f"Task {task_id} not found for cancellation.")
            return False

    async def get_task_status(self) -> dict[str, bool]:
        async with self._lock:
            return {tid: (ti.status == "running") for tid, ti in self.tasks.items()}

    async def run_gather_with_concurrency(
            self,
            coro_func: Callable[..., Awaitable[Any]],
            args_tuple_list: list[tuple],
            task_timeout: float | None = None,
            global_timeout: float | None = None,
            jitter: float | None = 3.0
    ) -> list[Any]:
        coro_name = self.get_coro_func_name(coro_func)
        results: list[Any] = [None] * len(args_tuple_list)

        async def _worker(index: int, args: tuple):
            if jitter and jitter > 0:
                await anyio.sleep(random.uniform(0, jitter))

            async with self._global_limiter:
                try:
                    logger.debug(f"Task-{index} ({coro_name}) started.")
                    if task_timeout and task_timeout > 0:
                        with fail_after(task_timeout):
                            res = await coro_func(*args)
                    else:
                        res = await coro_func(*args)
                    results[index] = res
                except TimeoutError:
                    logger.error(f"Task-{index} ({coro_name}) timed out (single task limit).")
                    results[index] = None
                except get_cancelled_exc_class():
                    logger.debug(f"Task-{index} ({coro_name}) cancelled.")
                    # 批量任务中，由于是 gather，通常不向上抛出取消，除非外部整个取消
                    # 但如果是 global_timeout 触发的，这里会被取消
                    pass
                except Exception as inner_exc:
                    logger.error(f"Task-{index} ({coro_name}) failed: {inner_exc}")
                    results[index] = None

        try:
            # move_on_after 用于处理 global_timeout，超时后 scope 会被取消，
            # 导致 TaskGroup 内的所有 _worker 被取消
            with move_on_after(global_timeout) as scope:
                async with create_task_group() as tg:
                    for i, args_tuple in enumerate(args_tuple_list):
                        tg.start_soon(_worker, i, args_tuple)

            if scope.cancelled_caught:
                logger.warning(f"Batch task ({coro_name}) hit global timeout {global_timeout}s.")
        except Exception as e:
            logger.error(f"Batch task ({coro_name}) unexpected error: {e}")

        return results

    # ---------- Synchronous Offloading APIs ----------

    async def run_in_thread(
            self,
            sync_func: Callable[..., Any],
            *,
            args_tuple: tuple | None = None,
            kwargs_dict: dict | None = None,
            timeout: float | None = None,
            cancellable: bool = False
    ) -> Any:
        return await self._execute_sync(
            sync_func, args_tuple or (), kwargs_dict or {}, timeout, cancellable, "thread"
        )

    async def run_in_process(
            self,
            sync_func: Callable[..., Any],
            *,
            args_tuple: tuple | None = None,
            kwargs_dict: dict | None = None,
            timeout: float | None = None,
            cancellable: bool = False
    ) -> Any:
        return await self._execute_sync(
            sync_func, args_tuple or (), kwargs_dict or {}, timeout, cancellable, "process"
        )

    async def run_in_threads(
            self,
            sync_func: Callable[..., Any],
            *,
            args_tuple_list: list[tuple] | None = None,
            kwargs_dict_list: list[dict] | None = None,
            timeout: float | None = None,
            cancellable: bool = False
    ) -> list[Any]:
        return await self._run_batch_sync(
            sync_func, args_tuple_list, kwargs_dict_list, timeout, cancellable, "thread"
        )

    async def run_in_processes(
            self,
            sync_func: Callable[..., Any],
            *,
            args_tuple_list: list[tuple] | None = None,
            kwargs_dict_list: list[dict] | None = None,
            timeout: float | None = None,
            cancellable: bool = False
    ) -> list[Any]:
        return await self._run_batch_sync(
            sync_func, args_tuple_list, kwargs_dict_list, timeout, cancellable, "process"
        )

    async def _run_batch_sync(
            self,
            sync_func: Callable,
            args_list: list[tuple] | None,
            kwargs_list: list[dict] | None,
            timeout: float | None,
            cancellable: bool,
            backend: Literal["thread", "process"]
    ) -> list[Any]:
        args_list = args_list or []
        kwargs_list = kwargs_list or [None] * len(args_list)  # type: ignore
        if len(kwargs_list) != len(args_list):
            raise ValueError("args and kwargs lists must be same length")

        results: list[Any] = [None] * len(args_list)
        func_name = self.get_coro_func_name(sync_func)

        async def _worker(idx, a, k):
            bound = partial(sync_func, *(a or ()), **(k or {}))
            async with self._global_limiter:
                try:
                    # 包装执行逻辑，显式分支处理
                    async def _run():
                        if backend == "thread":
                            return await to_thread.run_sync(
                                bound, cancellable=cancellable, limiter=self._thread_limiter
                            )
                        else:
                            return await to_process.run_sync(
                                bound, cancellable=cancellable, limiter=self._process_limiter
                            )

                    if timeout and timeout > 0:
                        with fail_after(timeout):
                            res = await _run()
                    else:
                        res = await _run()

                    results[idx] = res
                except TimeoutError:
                    logger.error(f"{backend}-{idx} ({func_name}) timed out.")
                except get_cancelled_exc_class():
                    logger.debug(f"{backend}-{idx} ({func_name}) cancelled.")
                except Exception as e:
                    logger.error(f"{backend}-{idx} ({func_name}) failed: {e}")

        async with create_task_group() as tg:
            for i, (args, kwargs) in enumerate(zip(args_list, kwargs_list)):
                tg.start_soon(_worker, i, args, kwargs)

        return results
