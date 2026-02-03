from decimal import Decimal


def is_safe_float_range(value: Decimal, max_abs_value: float = 1e15, max_decimal_places: int = 6) -> bool:
    """
    判断 Decimal 值是否在安全的浮点数范围内。

    用于决定 Decimal 是否可以安全地转换为 float，而不会丢失精度或造成前端兼容性问题。

    Args:
        value: 要检查的 Decimal 值
        max_abs_value: 最大绝对值范围（默认 1e15）
        max_decimal_places: 最大小数位数（默认 6 位）

    Returns:
        bool: 如果值在安全范围内返回 True，否则返回 False

    Examples:
        >>> from decimal import Decimal
        >>> is_safe_float_range(Decimal("123.45"))
        True
        >>> is_safe_float_range(Decimal("123.1234567"))  # 超过 6 位小数
        False
        >>> is_safe_float_range(Decimal("1e16"))  # 超过 1e15
        False
    """
    # 检查绝对值范围
    if not (-max_abs_value < value < max_abs_value):
        return False

    # 检查小数位数
    # Decimal.as_tuple().exponent 返回指数值
    # 对于小数，exponent 为负数，例如 0.01 的 exponent 为 -2
    # 如果 exponent >= -max_decimal_places，表示小数位数不超过限制
    # 注意：当 Decimal 为 NaN 或 Infinity 时，exponent 是字符串类型 ('n', 'N', 'F')
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        # NaN 或 Infinity 不在安全范围内
        return False
    return exponent >= -max_decimal_places
