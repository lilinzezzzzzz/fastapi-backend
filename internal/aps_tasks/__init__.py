from internal.aps_tasks.tasks import number_sum
from pkg.aps_task_manager import ApsSchedulerTool, new_aps_scheduler_tool

apscheduler_manager: ApsSchedulerTool = new_aps_scheduler_tool(timezone="UTC", max_instances=50)

apscheduler_manager.register_cron_job(
    number_sum,
    cron_kwargs={"minute": "*/15", "second": 0}
)
