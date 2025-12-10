def unique_list(values: list | tuple, exclude_none=True) -> list:
    seen = {}
    for value in values:
        if value is None and exclude_none:
            continue

        if value in seen:
            continue

        seen[value] = None

    unique_values = list(seen.keys())
    return unique_values


def ensure_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


# 取两个列表不同的元素，比如[1, 2, 3], [3, 4, 5] => [1, 2, 4, 5]
def diff_list(a: list, b: list) -> list:
    return list(set(a).symmetric_difference(set(b)))


# 列表去重
def unique_iterable(iterable: list | tuple | set) -> list:
    """
    对可迭代对象进行去重，并保持原有顺序。

    :param iterable: 输入的可迭代对象（list, tuple 或 set）
    :return: 去重后的 list
    :raises ValueError: 如果输入不是 list, tuple 或 set 类型
    """
    if isinstance(iterable, (list, tuple)):
        return list(dict.fromkeys(iterable))
    elif isinstance(iterable, set):
        return sorted(iterable)  # 若需保留顺序，set 不合适
    else:
        raise ValueError("Input must be a list, tuple, or set")


# 合并列表
def merge_list(a: list, b: list) -> list:
    return list(set(a).union(set(b)))
