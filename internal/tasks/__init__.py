"""任务调度层

职责：
- Celery 任务包装（装饰器 + 调度）
- 定时任务配置（Beat Schedule）
- APScheduler 任务导入

注意：业务逻辑应放在 services 层，此处只做调度和协调
"""

from internal.tasks.celery_tasks import (
    clean_expired_tokens,
    generate_daily_report,
    heartbeat,
    number_sum,
    send_welcome_email,
    sync_user_data,
    warmup_cache,
)
from internal.tasks.scheduler import (
    CELERY_INCLUDE_MODULES,
    CELERY_TASK_ROUTES,
    STATIC_BEAT_SCHEDULE,
)

__all__ = [
    # Celery 任务
    "number_sum",
    "clean_expired_tokens",
    "generate_daily_report",
    "send_welcome_email",
    "sync_user_data",
    "heartbeat",
    "warmup_cache",
    # 调度配置
    "CELERY_INCLUDE_MODULES",
    "CELERY_TASK_ROUTES",
    "STATIC_BEAT_SCHEDULE",
]
