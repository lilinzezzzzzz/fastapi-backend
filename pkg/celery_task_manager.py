import asyncio
from collections.abc import Mapping, Sequence, Callable, Coroutine
from datetime import datetime
from typing import Any

from celery import Celery, chain, chord, group, signals
from celery.result import AsyncResult, GroupResult
from celery.schedules import crontab, schedule
from kombu.utils.uuid import uuid

from pkg.logger_tool import logger

try:
    # 尝试导入 RedBeat 的调度条目类，用于动态任务管理
    from redbeat import RedBeatSchedulerEntry

    HAS_REDBEAT = True
except ImportError:
    HAS_REDBEAT = False

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
            redbeat_redis_url: str | None = None,  # 新增：用于动态定时任务
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
            "task_serializer": "json",
            "accept_content": ["json"],
            "result_serializer": "json",
            "worker_hijack_root_logger": False,
            "broker_connection_retry_on_startup": True,
            "result_extended": True,
        }

        # --- 动态定时任务配置 (RedBeat) ---
        if redbeat_redis_url:
            if not HAS_REDBEAT:
                logger.warning("RedBeat URL provided but 'celery-redbeat' not installed. Dynamic scheduling disabled.")
            else:
                conf["redbeat_redis_url"] = redbeat_redis_url
                conf["redbeat_key_prefix"] = f"{app_name}:redbeat"
                # 指定 Scheduler 为 RedBeat
                # 注意：启动 beat 时需要指定: celery -A ... beat -S redbeat.RedBeatScheduler
                # 这里仅做配置，实际生效取决于 Beat 进程的启动方式

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
            **options
        }

        # 处理 Retry Policy 等特殊头部逻辑可在此处扩展...

        return self.app.send_task(
            name=task_name,
            args=args,
            kwargs=kwargs,
            **exec_options
        )

    @staticmethod
    def chain(*signatures) -> AsyncResult:
        """链式调用: task1 -> task2 -> task3"""
        return chain(*signatures).apply_async()

    @staticmethod
    def group(*signatures) -> GroupResult:
        """并发调用: [task1, task2, task3]"""
        return group(*signatures).apply_async()

    @staticmethod
    def chord(header, body) -> AsyncResult:
        """回调模式: group(header) 完成后 -> body"""
        return chord(header)(body).apply_async()

    # ------------------------------
    # 2. 动态定时任务 (替代 APScheduler)
    # ------------------------------
    def add_periodic_task(
            self,
            task_name: str,
            schedule_type: str,  # 'cron' or 'interval'
            schedule_value: dict | int,
            args_tuple: tuple = (),
            kwargs_dict: dict = None,
            name: str = None
    ):
        """
        动态添加定时任务 (建议配合 celery-redbeat 使用)
        :param args_tuple
        :param kwargs_dict
        :param task_name: 具体的任务函数名 'tasks.add'
        :param schedule_type: 'cron' 或 'interval'
        :param schedule_value:
               - 如果 type='interval', 传秒数 (int)
               - 如果 type='cron', 传 dict: {'minute': '*/5', 'hour': '*'}
        :param name: 任务唯一标识 (ID)，用于后续删除或修改
        """
        if not name:
            name = f"{task_name}:{uuid()}"

        # 1. 构建 Schedule 对象
        if schedule_type == 'cron':
            # 默认值为 *
            cron_conf = {
                'minute': '*', 'hour': '*', 'day_of_week': '*',
                'day_of_month': '*', 'month_of_year': '*'
            }
            if isinstance(schedule_value, dict):
                cron_conf.update(schedule_value)

            check_schedule = crontab(**cron_conf)
        elif schedule_type == 'interval':
            check_schedule = schedule(run_every=float(schedule_value))
        else:
            raise ValueError("schedule_type must be 'cron' or 'interval'")

        # 2. 如果安装了 RedBeat，直接写入 Redis 实现动态生效
        if HAS_REDBEAT and self.app.conf.get("redbeat_redis_url"):
            try:
                entry = RedBeatSchedulerEntry(
                    name=name,
                    task=task_name,
                    schedule=check_schedule,
                    args=args_tuple,
                    kwargs=kwargs_dict,
                    app=self.app
                )
                entry.save()
                logger.info(f"Dynamic periodic task '{name}' added via RedBeat.")
                return name
            except Exception as e:
                logger.error(f"Failed to add RedBeat task: {e}")
                raise e

        # 3. 如果没有 RedBeat，修改内存配置 (仅当前进程生效，生产环境 Beat 进程通常独立，无法感知)
        else:
            logger.warning(
                "Adding task to in-memory schedule. If Celery Beat is in a separate process, this WILL NOT work.")
            self.app.conf.beat_schedule[name] = {
                "task": task_name,
                "schedule": check_schedule,
                "args": args_tuple,
                "kwargs": kwargs_dict
            }
            return name

    def remove_periodic_task(self, name: str):
        """移除动态定时任务"""
        if HAS_REDBEAT and self.app.conf.get("redbeat_redis_url"):
            try:
                # 尝试加载并删除
                try:
                    entry = RedBeatSchedulerEntry.from_key(f"{self.app.conf.redbeat_key_prefix}:{name}", app=self.app)
                    entry.delete()
                    logger.info(f"Dynamic periodic task '{name}' removed via RedBeat.")
                except KeyError:
                    logger.warning(f"Task {name} not found in RedBeat.")
            except Exception as e:
                logger.error(f"Failed to remove RedBeat task: {e}")
        else:
            if name in self.app.conf.beat_schedule:
                del self.app.conf.beat_schedule[name]
                logger.info(f"In-memory task '{name}' removed.")
            else:
                logger.warning(f"Task '{name}' not found in memory schedule.")

    # ------------------------------
    # 3. 查询与检查
    # ------------------------------
    def get_result(self, task_id: str) -> Any:
        return AsyncResult(task_id, app=self.app).result

    def get_status(self, task_id: str) -> str:
        return AsyncResult(task_id, app=self.app).state

    def revoke(self, task_id: str, terminate: bool = False):
        self.app.control.revoke(task_id, terminate=terminate)

    @staticmethod
    def register_worker_hooks(
            on_startup: LifecycleHook | None = None,
            on_shutdown: LifecycleHook | None = None
    ):
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
                        # 处理异步关闭的通用逻辑
                        loop = asyncio.get_event_loop_policy().get_event_loop()
                        if loop.is_running():
                            loop.create_task(on_shutdown())
                        else:
                            loop.run_until_complete(on_shutdown())
                    else:
                        on_shutdown()
                    logger.info("Worker shutdown hook executed successfully.")
                except Exception as e:
                    logger.warning(f"Worker shutdown hook error: {e}")


def import_os():
    import os
    return os
