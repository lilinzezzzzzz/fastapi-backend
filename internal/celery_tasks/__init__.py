import asyncio
import os

from celery import signals

from internal.config.setting import setting
from internal.infra.celery_db_session import close_async_celery_db, init_async_celery_db
from pkg import SYS_NAMESPACE
from pkg.celery_task_manager import CeleryClient
from pkg.logger_tool import logger


@signals.worker_process_init.connect
def _init_db_in_worker_process_init(**_):
    # 子进程里初始化，避免在 fork 前创建资源
    init_async_celery_db()
    logger.info(f"[init] worker_process_init ok (pid={os.getpid()})")

@signals.worker_process_shutdown.connect
def _close_db_in_worker_process_shutdown(**_):
    # Celery 信号处理器是同步函数，这里直接跑一个短暂 event loop 最稳
    asyncio.run(close_async_celery_db())
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