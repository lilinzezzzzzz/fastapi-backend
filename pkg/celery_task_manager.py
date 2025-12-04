import asyncio
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, cast, Union

from celery import Celery, chain, chord, group, signals, states
from celery.result import AsyncResult, GroupResult
from celery.schedules import crontab, schedule
from kombu.utils.uuid import uuid

# 引入之前的数据库/Redis管理函数 (确保路径正确)
from internal.infra.database import init_db, close_db
# from internal.infra.default_redis import init_redis, close_redis # 如果需要Redis
from pkg.logger_tool import logger

try:
    # 尝试导入 RedBeat 的调度条目类，用于动态任务管理
    from redbeat import RedBeatSchedulerEntry

    HAS_REDBEAT = True
except ImportError:
    HAS_REDBEAT = False


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

    def chain(self, *signatures) -> AsyncResult:
        """链式调用: task1 -> task2 -> task3"""
        return chain(*signatures).apply_async()

    def group(self, *signatures) -> GroupResult:
        """并发调用: [task1, task2, task3]"""
        return group(*signatures).apply_async()

    def chord(self, header, body) -> AsyncResult:
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
        : param args
        : param kwargs
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


# =============================================================================
# 信号处理 (Signal Handlers) - 自动管理 DB 连接
# =============================================================================

@signals.worker_process_init.connect
def setup_worker_process_resources(**kwargs):
    """
    【重要】子进程初始化
    每个 Worker 进程(Fork出来的)启动时，初始化独立的数据库连接池。
    """
    try:
        logger.info(f"Initializing DB for worker process (PID: {import_os().getpid()})...")
        init_db()
        # init_redis() # 如有需要
    except Exception as e:
        logger.critical(f"Worker process initialization failed: {e}")
        raise e


@signals.worker_process_shutdown.connect
def teardown_worker_process_resources(**kwargs):
    """
    【重要】子进程关闭
    """
    logger.info("Closing DB for worker process...")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(close_db())
        else:
            asyncio.run(close_db())
    except Exception as e:
        # 进程即将销毁，记录日志即可
        logger.warning(f"Error closing DB in worker: {e}")


@signals.worker_init.connect
def setup_main_process(**kwargs):
    """父进程启动 (Main Process) - 通常不做数据库连接"""
    logger.info("Celery Main Process Started.")


@signals.worker_shutdown.connect
def teardown_main_process(**kwargs):
    """父进程关闭"""
    logger.info("Celery Main Process Stopped.")


def import_os():
    import os
    return os
