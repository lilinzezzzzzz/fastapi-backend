# pkg/aps_task_manager.py

from collections import deque
from collections.abc import Callable
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pkg.logger_tool import logger


class ApsSchedulerManager:
    """一个简单稳妥的 AsyncIO APScheduler 封装。

    特性：
    - 统一 start()/shutdown()，可重复调用且幂等
    - 新增 register_* 系列：先登记、后启动；也支持已启动后即时添加
    - 支持按任务默认：max_instances / jitter / coalesce / misfire_grace_time
    - 逐个出队灌入 pending 任务，避免“部分成功”后的重复添加
    - 允许按需暴露底层 scheduler

    术语说明：
    - jitter（秒）：每次触发点随机偏移 ±jitter 秒，打散集中触发
    - coalesce：当调度被阻塞导致错过多次触发时，是否合并为一次执行
    - misfire_grace_time（秒）：错过触发点后，在这个宽限期内仍允许立即补跑
    """

    def __init__(
        self,
        *,
        timezone: str = "UTC",
        job_defaults: dict[str, Any] | None = None,
        max_instances: int = 50,
        # 新增：类级默认（可被单个 job 覆盖）
        default_jitter: int | None = 7,
        default_coalesce: bool | None = True,
        default_misfire_grace_time: int | None = 60
    ) -> None:
        # 组合调度器层面的 job_defaults（只设置未显式传入的项）
        base_job_defaults = dict(job_defaults or {})
        if "coalesce" not in base_job_defaults and default_coalesce is not None:
            base_job_defaults["coalesce"] = default_coalesce
        if "misfire_grace_time" not in base_job_defaults and default_misfire_grace_time is not None:
            base_job_defaults["misfire_grace_time"] = default_misfire_grace_time
        # 不在 scheduler 的 job_defaults 里设置 max_instances / jitter
        # max_instances 继续由本类统一填充，jitter 由本类做版本兼容填充

        self._scheduler = AsyncIOScheduler(timezone=timezone, job_defaults=base_job_defaults)

        # 给所有 job 的默认 max_instances；单个 job 可覆盖
        self._default_max_instances = max_instances
        self._default_jitter = default_jitter
        self._default_coalesce = default_coalesce
        self._default_misfire_grace_time = default_misfire_grace_time

        self._started: bool = False

        # 在 start() 前登记任务（存放“调用 add_job 的参数”）
        # 元素: tuple[func, args(tuple), kwargs(dict)]
        self._pending_jobs: deque[
            tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]
        ] = deque()

    # ------------------------- 基础生命周期 -------------------------
    def start(self) -> None:
        """启动 Scheduler（幂等）。"""
        if self._started:
            logger.debug("Scheduler already started; skip start().")
            return

        # 在真正 start() 之前，把 pending 的任务逐个出队并 add_job()
        while self._pending_jobs:
            func, args, kwargs = self._pending_jobs.popleft()
            job = self._scheduler.add_job(func, *args, **kwargs)
            logger.info(f"[startup] Added job: id={job.id}, trigger={job.trigger}")

        logger.info("Starting scheduler…")
        try:
            self._scheduler.start()
            self._started = True
        except Exception as e:  # noqa: BLE001
            logger.error(f"Scheduler startup error: {e}")
            raise
        logger.info("Scheduler started successfully")

    async def shutdown(self, *, wait: bool = True) -> None:
        """关闭 Scheduler（幂等）。"""
        if not self._started:
            logger.debug("Scheduler not started; skip shutdown().")
            return
        logger.info("Stopping scheduler…")
        try:
            self._scheduler.shutdown(wait=wait)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Scheduler shutdown error: {e}")
            raise
        else:
            logger.info("Scheduler stopped gracefully")
        finally:
            self._started = False

    # ------------------------- 新增：先登记、后启动 -------------------------
    def _ensure_default_job_options(self, kwargs: dict[str, Any]) -> None:
        """为单个 job 填充缺省选项（若调用方未设置）。"""
        kwargs.setdefault("max_instances", self._default_max_instances)
        if self._default_jitter is not None:
            kwargs.setdefault("jitter", self._default_jitter)
        if self._default_coalesce is not None:
            kwargs.setdefault("coalesce", self._default_coalesce)
        if self._default_misfire_grace_time is not None:
            kwargs.setdefault("misfire_grace_time", self._default_misfire_grace_time)

    def register_job(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        """登记一个任务。未启动时进入队列；已启动则立即添加。

        用法与 `scheduler.add_job` 等价：
            register_job(my_func, 'interval', seconds=5, id='foo')
            register_job(my_func, 'trigger', minutes=30, id='bar')
            register_job(my_func, 'date', run_date=datetime(...), id='baz')

        可在 kwargs 覆盖：
            id / replace_existing / max_instances / jitter / coalesce / misfire_grace_time / executor / name ...
        """
        self._ensure_default_job_options(kwargs)
        job_id = kwargs.get("id", func.__name__)

        if self._started:
            job = self._scheduler.add_job(func, *args, **kwargs)
            logger.info(f"Added job: id={job.id}, trigger={job.trigger}")
        else:
            self._pending_jobs.append((func, args, kwargs))
            # 尽量打印有辨识度的触发器信息
            trigger = kwargs.get("trigger", args[0] if args else None)
            logger.info(f"Registered (pending) job: id={job_id}, trigger={trigger}")

        return job_id

    def register_cron_job(
        self,
        func: Callable[..., Any],
        *,
        job_id: str | None = None,
        replace_existing: bool = True,
        cron_kwargs: dict[str, Any],
        **job_options: Any,
    ) -> str:
        """登记一个 Cron 任务。"""
        if not cron_kwargs:
            raise ValueError("cron_kwargs cannot be empty")
        trigger = CronTrigger(**cron_kwargs)
        return self.register_job(
            func,
            trigger=trigger,
            id=(job_id or func.__name__),
            replace_existing=replace_existing,
            **job_options,
        )

    def register_interval_job(
        self,
        func: Callable[..., Any],
        *,
        job_id: str | None = None,
        replace_existing: bool = True,
        interval_kwargs: dict[str, Any],
        **job_options: Any,
    ) -> str:
        """登记一个 Interval 任务。"""
        if not interval_kwargs:
            raise ValueError("interval_kwargs cannot be empty")
        trigger = IntervalTrigger(**interval_kwargs)
        return self.register_job(
            func,
            trigger=trigger,
            id=(job_id or func.__name__),
            replace_existing=replace_existing,
            **job_options,
        )

    def register_date_job(
        self,
        func: Callable[..., Any],
        *,
        job_id: str | None = None,
        replace_existing: bool = True,
        date_kwargs: dict[str, Any],
        **job_options: Any,
    ) -> str:
        """登记一个 Date 一次性任务。"""
        if not date_kwargs:
            raise ValueError("date_kwargs cannot be empty")
        trigger = DateTrigger(**date_kwargs)
        return self.register_job(
            func,
            trigger=trigger,
            id=(job_id or func.__name__),
            replace_existing=replace_existing,
            **job_options,
        )

    # ------------------------- 查询/控制 -------------------------
    @property
    def scheduler(self) -> AsyncIOScheduler:
        return self._scheduler

    def get_job(self, job_id: str):
        return self._scheduler.get_job(job_id)

    def remove_job(self, job_id: str) -> None:
        self._scheduler.remove_job(job_id)
        logger.info(f"Removed job: id={job_id}")

    def pause_job(self, job_id: str) -> None:
        self._scheduler.pause_job(job_id)
        logger.info(f"Paused job: id={job_id}")

    def resume_job(self, job_id: str) -> None:
        self._scheduler.resume_job(job_id)
        logger.info(f"Resumed job: id={job_id}")

    def running(self) -> bool:
        return self._started


def new_aps_scheduler_tool(
    timezone: str,
    job_defaults: dict[str, Any] | None = None,
    max_instances: int = 50,
    *,
    default_jitter: int | None = None,
    default_coalesce: bool | None = True,
    default_misfire_grace_time: int | None = 60,
) -> ApsSchedulerManager:
    """工厂方法，便于集中配置默认行为。"""
    return ApsSchedulerManager(
        timezone=timezone,
        job_defaults=job_defaults,
        max_instances=max_instances,
        default_jitter=default_jitter,
        default_coalesce=default_coalesce,
        default_misfire_grace_time=default_misfire_grace_time,
    )


# ------------------------- 用法示例（可删） -------------------------
# from datetime import datetime, timedelta
# tool = new_aps_scheduler_tool(
#     timezone="UTC",
#     max_instances=50,
#     # scheduler 层面的默认（没传就用下方默认）：
#     # job_defaults={"coalesce": True, "misfire_grace_time": 60},
#     # 类级默认（单个任务可覆盖）：
#     default_jitter=7,                  # 全局抖动 ±7 秒
#     default_coalesce=True,             # 合并滞后触发
#     default_misfire_grace_time=60,     # 允许 60 秒内补跑
# )
# tool.register_cron_job(my_task, cron_kwargs={"minute": "*", "second": 0}, jitter=10)  # 覆盖为 ±10 秒
# tool.register_interval_job(heartbeat, interval_kwargs={"seconds": 30})
# tool.register_date_job(one_shot, date_kwargs={"run_date": datetime.utcnow() + timedelta(minutes=1)}, coalesce=True)
# tool.start()
