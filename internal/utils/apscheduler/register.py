from internal.tasks.demo_task import handle_number_sum
from internal.utils.apscheduler import _apscheduler_manager


def _register_tasks():
    _apscheduler_manager.register_cron(handle_number_sum, cron_kwargs={"minute": "*/15", "second": 0})
