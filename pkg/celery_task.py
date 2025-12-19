import asyncio
from collections.abc import Callable, Coroutine, Mapping, Sequence
from datetime import datetime
from typing import Any, cast

from celery import Celery, chain, chord, group, signals
from celery.result import AsyncResult, GroupResult
from kombu.utils.uuid import uuid

from pkg.async_logger import logger

LifecycleHook = Callable[[], Any] | Callable[[], Coroutine[Any, Any, Any]]


class CeleryClient:
    """
    Celery 工具类：封装任务提交、编排、状态查询及动态定时任务管理。
    """

    def __init__(
        self,
        app_name: str,
        broker_url: str,
        backend_url: str | None = None,
        include: Sequence[str] | None = None,
        task_routes: Mapping[str, Mapping[str, Any]] | None = None,
        task_default_queue: str = "default",
        timezone: str = "UTC",
        enable_utc: bool = True,
        beat_schedule: dict[str, Any] | None = None,
        **extra_conf: Any,
    ) -> None:
        self.queue = task_default_queue
        self.app = Celery(app_name, broker=broker_url, backend=backend_url, include=include)

        # 基础配置
        conf = {
            "timezone": timezone,
            "enable_utc": enable_utc,
            "task_default_queue": task_default_queue,
            "task_routes": task_routes or {},
            "beat_schedule": beat_schedule or {},
            "task_serializer": "json",
            "accept_content": ["json"],
            "result_serializer": "json",
            "worker_hijack_root_logger": False,
            "broker_connection_retry_on_startup": True,
            "result_extended": True,
        }

        conf.update(extra_conf or {})
        self.app.conf.update(conf)

    # ------------------------------
    # 1. 提交/编排任务
    # ------------------------------
    def submit(
        self,
        *,
        task_name: str,
        args: tuple | list | None = None,
        kwargs: dict | None = None,
        task_id: str | None = None,
        countdown: int | float | None = None,
        eta: datetime | None = None,
        priority: int | None = None,
        queue: str | None = None,
        **options: Any,
    ) -> AsyncResult:
        """
        提交异步任务 (Apply Async Wrapper)
        """
        task_id = task_id or uuid()
        args = tuple(args) if args else ()
        kwargs = kwargs or {}

        # 构造执行选项
        exec_options = {
            "task_id": task_id,
            "countdown": countdown,
            "eta": eta,
            "priority": priority,
            "queue": queue or self.queue,
            **options,
        }

        # 处理 Retry Policy 等特殊头部逻辑可在此处扩展...

        return self.app.send_task(name=task_name, args=args, kwargs=kwargs, **exec_options)

    @staticmethod
    def chain(*signatures) -> AsyncResult:
        """链式调用: task1 -> task2 -> task3"""
        return chain(*signatures).apply_async()

    @staticmethod
    def group(*signatures) -> GroupResult:
        """并发调用: [task1, task2, task3]"""
        return cast(GroupResult, cast(object, group(*signatures).apply_async()))

    @staticmethod
    def chord(header, body) -> AsyncResult:
        """回调模式: group(header) 完成后 -> body"""
        return chord(header)(body).apply_async()

    # ------------------------------
    # 2. 查询与检查
    # ------------------------------
    def get_result(self, task_id: str, timeout: float = None, propagate: bool = True) -> Any:
        """
        获取任务结果。
        :param task_id: 任务 ID
        :param timeout: 等待超时时间（秒）
        :param propagate: 如果为 True，任务失败会抛出异常；如果为 False，返回异常对象
        :return: 任务执行结果
        """
        result_obj = AsyncResult(task_id, app=self.app)
        # 推荐使用 get，它会处理等待逻辑和异常抛出
        return result_obj.get(timeout=timeout, propagate=propagate)

    def get_status(self, task_id: str) -> str:
        return AsyncResult(task_id, app=self.app).state

    def revoke(self, task_id: str, terminate: bool = False):
        self.app.control.revoke(task_id, terminate=terminate)

    @staticmethod
    def register_worker_hooks(on_startup: LifecycleHook | None = None, on_shutdown: LifecycleHook | None = None):
        """
        注册 Worker 进程生命周期钩子（依赖注入）。
        用户可以将数据库初始化、Redis 连接等逻辑通过参数传入。

        :param on_startup: Worker 子进程启动时执行 (通常用于 init_db)
        :param on_shutdown: Worker 子进程关闭时执行 (通常用于 close_db)
        """

        # --- 1. 定义 Startup Handler ---
        if on_startup:

            @signals.worker_process_init.connect(weak=False)
            def _wrapper_startup(**kwargs):
                logger.info("Executing registered worker startup hook...")
                try:
                    # 判断是否是异步函数 (虽然 worker_init 通常建议同步，但也兼容一下)
                    if asyncio.iscoroutinefunction(on_startup):
                        # 注意：Celery process init 时 loop 可能未准备好，通常运行同步代码更稳
                        # 这里简单处理，如果真的是 async，尝试 run
                        asyncio.run(on_startup())
                    else:
                        on_startup()
                    logger.info("Worker startup hook executed successfully.")
                except Exception as e:
                    logger.critical(f"Worker startup hook failed: {e}")
                    raise e

        # --- 2. 定义 Shutdown Handler ---
        if on_shutdown:

            @signals.worker_process_shutdown.connect(weak=False)
            def _wrapper_shutdown(**kwargs):
                logger.info("Executing registered worker shutdown hook...")
                try:
                    if asyncio.iscoroutinefunction(on_shutdown):
                        # 强制同步运行，确保清理完成才退出
                        asyncio.run(on_shutdown())
                    else:
                        on_shutdown()
                    logger.info("Worker shutdown hook executed successfully.")
                except Exception as e:
                    logger.warning(f"Worker shutdown hook error: {e}")
