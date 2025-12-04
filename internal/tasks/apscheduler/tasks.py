from pkg.logger_tool import logger


def number_sum(num1: int, num2: int):
    """
    计算两个数字的和
    :param num1: 数字1
    :param num2: 数字2
    :return: 两个数字的和
    """
    logger.info(f"计算两个数字的和: {num1} + {num2} = {num1 + num2}")
