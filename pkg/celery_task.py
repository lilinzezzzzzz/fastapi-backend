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

    def _inject_defaults(self, options: dict) -> dict:
        """内部辅助：注入默认队列等配置"""
        options = options or {}
        if "queue" not in options and self.queue:
            options["queue"] = self.queue
        # 这里可以继续注入其他实例级默认配置
        return options

    def chain(self, *signatures, **options) -> AsyncResult:
        """
        链式调用: task1 -> task2 -> task3
        :param signatures: 任务签名列表
        :param options: apply_async 的执行参数 (如 queue, countdown, retry 等)
        """
        # 1. 创建链式对象
        workflow = chain(*signatures)

        # 2. 绑定当前 App 实例 (防止多实例环境下的混乱)
        workflow.app = self.app

        # 3. 注入默认配置 (如默认队列)
        exec_options = self._inject_defaults(options)

        # 4. 执行
        return workflow.apply_async(**exec_options)

    def group(self, *signatures, **options) -> GroupResult:
        """
        并发调用: [task1, task2, task3]
        """
        workflow = group(*signatures)
        workflow.app = self.app
        exec_options = self._inject_defaults(options)

        # 使用 cast 解决类型提示报错 (参考之前的修复)
        return cast(GroupResult, workflow.apply_async(**exec_options))

    def chord(self, header, body, **options) -> AsyncResult:
        """
        回调模式: group(header) 完成后 -> body
        注意：body 任务必须接受 header 的结果列表作为第一个参数。
        """
        # Celery 的 chord 初始化通常建议显式绑定 app
        workflow = chord(header, body=body, app=self.app)

        exec_options = self._inject_defaults(options)

        return workflow.apply_async(**exec_options)

    # ------------------------------
    # 2. 查询与检查
    # ------------------------------
    def get_result(self, task_id: str, timeout: int = 10, propagate: bool = True) -> Any:
        """
        获取结果，默认等待 10秒。
        """
        try:
            return AsyncResult(task_id, app=self.app).get(timeout=timeout, propagate=propagate)
        except Exception as e:
            # 根据需要处理超时或任务异常
            raise e

    def get_status(self, task_id: str) -> str:
        return AsyncResult(task_id, app=self.app).state

    def revoke(self, task_id: str, terminate: bool = False):
        self.app.control.revoke(task_id, terminate=terminate)

    @staticmethod
    def register_worker_hooks(on_startup: LifecycleHook | None = None, on_shutdown: LifecycleHook | None = None):
        # 使用 dispatch_uid 防止重复注册

        if on_startup:

            @signals.worker_process_init.connect(weak=False, dispatch_uid="pkg_worker_startup")
            def _wrapper_startup(**kwargs):
                logger.info("Executing worker startup hook...")
                if asyncio.iscoroutinefunction(on_startup):
                    asyncio.run(on_startup())
                else:
                    on_startup()

        if on_shutdown:

            @signals.worker_process_shutdown.connect(weak=False, dispatch_uid="pkg_worker_shutdown")
            def _wrapper_shutdown(**kwargs):
                logger.info("Executing worker shutdown hook...")
                # 必须同步等待清理完成，严禁使用 create_task
                if asyncio.iscoroutinefunction(on_shutdown):
                    asyncio.run(on_shutdown())
                else:
                    on_shutdown()
