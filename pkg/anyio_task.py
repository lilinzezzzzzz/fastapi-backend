import multiprocessing
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

import anyio
from anyio import CancelScope, CapacityLimiter, create_task_group, fail_after, to_process, to_thread, move_on_after
from anyio.abc import TaskGroup

from pkg.logger_tool import logger

CPU = max(1, multiprocessing.cpu_count())
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
        self._tg = await create_task_group().__aenter__()  # 持久 TaskGroup
        self._tg_started = True
        logger.info("AsyncTaskManagerAnyIO started.")

    async def shutdown(self):
        logger.info("Shutting down AsyncTaskManagerAnyIO...")
        async with self._lock:
            for info in self.tasks.values():
                try:
                    info.scope.cancel()
                except Exception as e:
                    logger.warning(f"Error canceling task: {e}")
        if self._tg_started and self._tg is not None:
            try:
                await self._tg.__aexit__(None, None, None)
            finally:
                self._tg = None
                self._tg_started = False
        logger.info("AsyncTaskManagerAnyIO stopped.")

    # ---------- helpers ----------
    @staticmethod
    def get_coro_func_name(coro_func: Callable[..., Awaitable[Any]]) -> str:
        if getattr(coro_func, "__name__", None) == "<lambda>":
            raise ValueError("Lambda functions are not supported for task tracking!")

        # 处理 partial 对象
        if isinstance(coro_func, partial):
            func = coro_func.func
            if hasattr(func, "__self__"):
                return f"{func.__self__.__class__.__name__}.{func.__name__}"
            elif hasattr(func, "__name__"):
                return func.__name__
            else:
                return "partial"

        if hasattr(coro_func, "__self__"):
            return f"{coro_func.__self__.__class__.__name__}.{coro_func.__name__}"
        return coro_func.__name__

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
                logger.info(f"Task {coro_name} {task_id} started.")

                if timeout and timeout > 0:
                    with fail_after(timeout):
                        result = await coro_func(*args_tuple, **kwargs_dict)
                else:
                    result = await coro_func(*args_tuple, **kwargs_dict)

                info.status = "completed"
                info.result = result
                logger.info(f"Task {coro_name} {task_id} completed.")

        except TimeoutError as te:
            info.status = "timeout"
            info.exception = te
            logger.error(f"Task {coro_name} {task_id} timed out after {timeout} seconds.")
        except BaseException as e:
            if isinstance(e, anyio.get_cancelled_exc_class()):
                info.status = "cancelled"
                logger.info(f"Task {coro_name} {task_id} cancelled.")
            else:
                info.status = "failed"
                info.exception = e
                logger.error(f"Task {coro_name} {task_id} failed, err={e}")
        finally:
            async with self._lock:
                self.tasks.pop(task_id, None)

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
        """仅进程内去重；多 worker 环境下可能重复提交。"""
        if not self._tg_started or self._tg is None:
            raise RuntimeError("AsyncTaskManagerAnyIO is not started. Call await start() first.")

        if isinstance(task_id, int):
            task_id = str(task_id)

        kwargs_dict = kwargs_dict or {}
        coro_name = self.get_coro_func_name(coro_func)

        async with self._lock:
            if len(self.tasks) >= self.max_queue:
                raise Exception(f"queue overflow: {self.max_queue}")

            if task_id in self.tasks:
                logger.warning(f"Task {task_id} already exists (same process).")
                return False

            scope = CancelScope()
            info = TaskInfo(task_id=task_id, name=coro_name, scope=scope)
            self.tasks[task_id] = info
            self._tg.start_soon(self._run_task_inner, info, coro_func, args_tuple, kwargs_dict, timeout)
        return True

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            info = self.tasks.get(task_id)
            if info:
                info.scope.cancel()
                logger.info(f"Task {task_id} cancelled.")
                return True
            logger.warning(f"Task {task_id} not found.")
            return False

    async def get_task_status(self) -> dict[str, bool]:
        async with self._lock:
            return {tid: (ti.status == "running") for tid, ti in self.tasks.items()}

    async def run_gather_with_concurrency(
            self,
            coro_func: Callable[..., Awaitable[Any]],
            args_tuple_list: list[tuple],
            task_timeout: float | None = None,  # 改名：更明确，控制单个任务
            global_timeout: float | None = None,  # 新增：控制整体耗时
            jitter: float | None = 3.0
    ) -> list[Any]:
        """
        并发执行多个相同函数的不同参数，支持单个超时和整体超时。

        Args:
            coro_func: 异步函数
            args_tuple_list: 参数元组列表
            task_timeout: 单个任务的超时时间（秒）。如果单个任务超时，该任务结果为 None
            global_timeout: 整体批量执行的超时时间（秒）。如果整体超时，未完成的任务结果为 None
            jitter: 随机抖动等待时间（秒）

        Returns:
            list[Any]: 结果列表。成功为结果值，失败或超时为 None。
        """
        coro_name = self.get_coro_func_name(coro_func)
        # 初始化结果列表，默认全为 None。
        # 这样如果整体超时导致任务被取消，未执行的任务位置自然保留为 None
        results: list[Any] = [None] * len(args_tuple_list)

        async def _wrapped(index: int, args: tuple):
            # jitter 逻辑保持不变
            if jitter and jitter > 0:
                await anyio.sleep(random.uniform(0, jitter))

            async with self._global_limiter:
                try:
                    logger.info(f"Task-{index} ({coro_name}, {args}) started.")

                    # --- 变更点1: 使用 task_timeout 控制单个任务 ---
                    if task_timeout and task_timeout > 0:
                        with fail_after(task_timeout):
                            res = await coro_func(*args)
                    else:
                        res = await coro_func(*args)

                    results[index] = res
                    logger.info(f"Task-{index} ({coro_name}, {args}) completed.")

                except TimeoutError:
                    # 单个任务超时
                    results[index] = None
                    logger.error(f"Task-{index} ({coro_name}, {args}) timed out after {task_timeout}s.")
                except BaseException as e:
                    # 任务被取消 (包括整体超时触发的取消) 或其他异常
                    # 注意：如果是整体超时触发的取消，这里会捕获到 CancelledError (包含在 BaseException 中)
                    # anyio 的 CancelledError 通常不需要手动处理，结果保持 None 即可
                    if isinstance(e, anyio.get_cancelled_exc_class()):
                        logger.debug(f"Task-{index} ({coro_name}) cancelled (likely global timeout).")
                    else:
                        results[index] = None
                        logger.error(f"Task-{index} ({coro_name}, {args}) failed. err={e}")

        # 如果 global_timeout 为 None 或 <=0，move_on_after(None) 相当于没有超时限制
        limit_scope = global_timeout if (global_timeout and global_timeout > 0) else None

        with move_on_after(limit_scope) as scope:
            async with create_task_group() as tg:
                for i, args_tuple in enumerate(args_tuple_list):
                    tg.start_soon(_wrapped, i, args_tuple)

        # --- 变更点3: 检测是否触发了整体超时 ---
        if scope.cancelled_caught:
            logger.warning(
                f"Batch task ({coro_name}) hit global timeout of {global_timeout}s. Returning partial results.")

        return results

    async def run_in_thread(
            self,
            sync_func: Callable[..., Any],
            *,
            args_tuple: tuple | None = None,
            kwargs_dict: dict | None = None,
            timeout: float | None = None,
            cancellable: bool = False
    ) -> Any:
        """
        用 AnyIO 线程池执行同步函数（不会阻塞事件循环）。
        - kwargs：同步函数的关键字参数（to_thread.run_sync 不接受 kwargs，因此用 partial 包装）
        - timeout：超时时间（秒），超时抛 anyio.TimeoutError
        - cancellable：是否允许取消在等待线程结果时生效（默认为 False）
        """
        func_name = self.get_coro_func_name(sync_func)
        logger.info(f"Task {func_name} started in a thread.")
        bound = partial(sync_func, *(args_tuple or ()), **(kwargs_dict or {}))
        if timeout and timeout > 0:
            with fail_after(timeout):
                return await to_thread.run_sync(bound, cancellable=cancellable, limiter=self._thread_limiter)
        return await to_thread.run_sync(bound, cancellable=cancellable, limiter=self._thread_limiter)

    async def run_in_process(
            self,
            sync_func: Callable[..., Any],
            *,
            args_tuple: tuple | None = None,
            kwargs_dict: dict | None = None,
            timeout: float | None = None,
            cancellable: bool = False
    ) -> Any:
        """
        用 AnyIO 进程池执行同步函数（CPU 密集/需隔离 GIL 的场景）。
        - 注意：func 必须是可 picklable 的顶层函数；args/kwargs 也需可序列化
        - Windows/macOS 默认 spawn，闭包/lambda/本地函数会失败
        - 取消语义：只能在等待结果时取消；真正的子进程中断取决于平台与 anyio 实现
        """
        func_name = self.get_coro_func_name(sync_func)
        logger.info(f"Task {func_name} started in process.")
        bound = partial(sync_func, *(args_tuple or ()), **(kwargs_dict or {}))
        if timeout and timeout > 0:
            with fail_after(timeout):
                return await to_process.run_sync(bound, cancellable=cancellable, limiter=self._process_limiter)
        return await to_process.run_sync(bound, cancellable=cancellable, limiter=self._process_limiter)

    async def run_in_threads(
            self,
            sync_func: Callable[..., Any],
            *,
            args_tuple_list: list[tuple] | None = None,
            kwargs_dict_list: list[dict] | None = None,
            timeout: float | None = None,
            cancellable: bool = False
    ) -> list[Any]:
        """
        使用 AnyIO 线程池并发执行一批 *同步* 函数调用（不会阻塞事件循环）。
        """
        args_tuple_list, kwargs_dict_list = self._check_rebuild_args_kwargs(args_tuple_list, kwargs_dict_list)

        results: list[Any] = [None] * len(args_tuple_list)
        func_name = self.get_coro_func_name(sync_func)

        async with create_task_group() as tg:
            for i, (args, kwargs) in enumerate(zip(args_tuple_list, kwargs_dict_list, strict=False)):
                bound = partial(
                    self._one_backend_sync_call,
                    index=i,
                    args_tuple=args,
                    kwargs_dict=kwargs,
                    sync_func=sync_func,
                    func_name=func_name,
                    timeout=timeout,
                    cancellable=cancellable,
                    run_sync_fn=to_thread.run_sync,  # 或 to_process.run_sync
                    backend_limiter=self._thread_limiter,  # 或 self._process_limiter
                    prefix="ThreadTask",  # 或 "ProcessTask"
                    results=results,
                )
                tg.start_soon(bound)  # type: ignore[arg-type]
        return results

    async def run_in_processes(
            self,
            sync_func: Callable[..., Any],
            *,
            args_tuple_list: list[tuple] | None = None,
            kwargs_dict_list: list[dict] | None = None,
            timeout: float | None = None,
            cancellable: bool = False
    ) -> list[Any]:
        """
        使用 AnyIO 进程池并发执行一批 *同步* 函数调用（适合 CPU 密集或需绕开 GIL 的场景）。
        """
        args_tuple_list, kwargs_dict_list = self._check_rebuild_args_kwargs(args_tuple_list, kwargs_dict_list)

        results: list[Any] = [None] * len(args_tuple_list)
        func_name = self.get_coro_func_name(sync_func)

        async with create_task_group() as tg:
            for i, (args, kwargs) in enumerate(zip(args_tuple_list, kwargs_dict_list, strict=False)):
                bound = partial(
                    self._one_backend_sync_call,
                    index=i,
                    args_tuple=args,
                    kwargs_dict=kwargs,
                    sync_func=sync_func,
                    func_name=func_name,
                    timeout=timeout,
                    cancellable=cancellable,
                    run_sync_fn=to_process.run_sync,
                    backend_limiter=self._process_limiter,
                    prefix="ProcessTask",
                    results=results,
                )
                tg.start_soon(bound)  # type: ignore[arg-type]
        return results

    @staticmethod
    def _check_rebuild_args_kwargs(args_tuple_list: list[tuple], kwargs_dict_list: list[dict] | None):
        args_tuple_list = args_tuple_list or []
        kwargs_dict_list = kwargs_dict_list or [None] * len(args_tuple_list)

        if len(kwargs_dict_list) != len(args_tuple_list):
            raise ValueError("args_tuple_list must be the same length as kwargs_dict_list.")
        return args_tuple_list, kwargs_dict_list

    async def _one_backend_sync_call(
            self,
            *,
            index: int,
            args_tuple: tuple,
            kwargs_dict: dict | None,
            sync_func: Callable[..., Any],
            func_name: str,
            timeout: float | None,
            cancellable: bool,
            run_sync_fn: Callable[..., Awaitable[Any]],  # to_thread.run_sync / to_process.run_sync
            backend_limiter: CapacityLimiter,  # self._thread_limiter / self._process_limiter
            prefix: str,  # "ThreadTask" / "ProcessTask"
            results: list[Any]
    ):
        """统一的单次同步调用执行器，供线程/进程批量跑时复用。"""
        bound = partial(sync_func, *(args_tuple or ()), **(kwargs_dict or {}))
        async with self._global_limiter:
            try:
                logger.info(f"{prefix}-{index} ({func_name}, args={args_tuple}, kwargs={kwargs_dict}) started.")
                if timeout and timeout > 0:
                    with fail_after(timeout):
                        res = await run_sync_fn(bound, cancellable=cancellable, limiter=backend_limiter)
                else:
                    res = await run_sync_fn(bound, cancellable=cancellable, limiter=backend_limiter)
                results[index] = res
                logger.info(f"{prefix}-{index} ({func_name}) completed.")
            except TimeoutError:
                results[index] = None
                logger.error(f"{prefix}-{index} ({func_name}) timed out after {timeout} seconds.")
            except BaseException as e:
                # 等待阶段的取消在这里体现为 CancelledError（线程/进程一致）
                if isinstance(e, anyio.get_cancelled_exc_class()):
                    logger.info(f"{prefix}-{index} ({func_name}) cancelled while awaiting result.")
                else:
                    logger.error(f"{prefix}-{index} ({func_name}) failed. err={e}")
                results[index] = None
