import asyncio
import os

from celery import signals

from internal.config.setting import setting
from internal.infra.database import init_db, close_db
from pkg import SYS_NAMESPACE
from pkg.celery_task_manager import CeleryClient
from pkg.logger_tool import logger


@signals.worker_process_init.connect
def _init_db_in_worker_process_init(**_):
    # 子进程里初始化，避免在 fork 前创建资源
    init_db()
    logger.info(f"[init] worker_process_init ok (pid={os.getpid()})")


@signals.worker_process_shutdown.connect
def _close_db_in_worker_process_shutdown(**_):
    """
        当 Worker 关闭时，优雅断开连接。
        注意：Celery 信号通常是同步的，但 SQLAlchemy dispose 是异步的。
        有些版本可以直接忽略 dispose，让操作系统回收资源；
        或者使用 asyncio.run(close_db()) (视 python/celery 版本而定)
        """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(close_db())
        else:
            asyncio.run(close_db())
    except Exception as e:
        logger.error(f"[close] close_db error: {e}, (pid={os.getpid()})")

    logger.info(f"[close] worker_process_shutdown ok (pid={os.getpid()})")


def celery_queue_name(name: str) -> str:
    return f"{SYS_NAMESPACE}-{name}"


default_queue = celery_queue_name("default")

default_celery_client = CeleryClient(
    app_name=f"{SYS_NAMESPACE}-ai-platform-celery",
    broker_url=setting.redis_url,
    backend_url=setting.redis_url,
    task_default_queue=default_queue,
    include=[
        # "internal.celery_tasks.bootstrap_db",
        # "internal.celery_tasks.test_task",
        # "internal.celery_tasks.model_evaluation"
    ],
    task_routes={
        # "internal.celery_tasks.test_task.*": {"queue": default_queue},
        # "internal.celery_tasks.model_evaluation.*": {"queue": default_queue},
    }
)

default_app = default_celery_client.app


class CeleryClientHub:
    __slots__ = ['__celery_cli_hub']

    def __init__(self):
        self.__celery_cli_hub: dict[str, CeleryClient] = {
            "default": default_celery_client
        }

    def all_cli(self) -> list[CeleryClient]:
        return list(self.__celery_cli_hub.values())

    def select_cli(self, app_name: str) -> CeleryClient:
        if app_name not in self.__celery_cli_hub:
            raise ValueError(f"app_name {app_name} not found")
        return self.__celery_cli_hub[app_name]

    def get_cli_names(self) -> list[str]:
        """获取所有应用名称"""
        return list(self.__celery_cli_hub.keys())

    def has_cli(self, app_name: str) -> bool:
        """检查是否存在指定应用"""
        return app_name in self.__celery_cli_hub


celery_cli_hub = CeleryClientHub()
default_celery_cli = celery_cli_hub.select_cli("default")
