from internal.tasks.task_handlers import handle_number_sum


async def number_sum(num1: int, num2: int):
    """
    计算两个数字的和
    :param num1: 数字1
    :param num2: 数字2
    :return: 两个数字的和
    """
    # 调用共享的异步任务处理函数
    return await handle_number_sum(num1, num2)
