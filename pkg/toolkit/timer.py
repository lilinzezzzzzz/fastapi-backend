import datetime


def format_iso_datetime(val: datetime.datetime, *, use_z: bool = True, timespec: str = "milliseconds") -> str:
    """
    将 datetime 对象格式化为 ISO 8601 字符串。
    - 有时区信息：保留时区并输出 ISO 格式
    - 无时区信息：假定为 UTC

    Args:
        val: 要格式化的 datetime 对象。
        use_z: 如果为 True 且时区为 UTC，输出 'Z' 格式；否则输出 '+00:00' 格式。
        timespec: 时间精度，可选值：'auto', 'hours', 'minutes', 'seconds', 'milliseconds', 'microseconds'。

    Returns:
        ISO 8601 格式的字符串。
    """
    if val.tzinfo is None:
        val = val.replace(tzinfo=datetime.UTC)

    iso_str = val.isoformat(timespec=timespec)

    if use_z and val.utcoffset() == datetime.timedelta(0):
        # 将 '+00:00' 替换为 'Z'
        return iso_str.replace("+00:00", "Z")

    return iso_str


def parse_iso_string(iso_string: str) -> datetime.datetime:
    """
    将 ISO 8601 格式的时间字符串解析为 datetime 对象。

    Args:
        iso_string: ISO 格式的时间字符串（例如 "2024-12-23T18:30:00Z" 或 "2024-12-23T18:30:00+00:00"）

    Returns:
        解析后的 datetime 对象。

    Raises:
        ValueError: 当字符串格式无效时。
    """
    try:
        # 处理 'Z' 结尾（表示 UTC）
        if iso_string.endswith("Z"):
            iso_string = iso_string[:-1] + "+00:00"

        return datetime.datetime.fromisoformat(iso_string)
    except ValueError as e:
        raise ValueError(f"Invalid ISO format string: {iso_string}") from e


def convert_to_utc(val: datetime.datetime) -> datetime.datetime:
    """
    将 datetime 转换为带 UTC 时区信息的 datetime。
    - 有时区信息：转换为 UTC
    - 无时区信息：假定已经是 UTC，直接添加时区标记

    Args:
        val: 要转换的 datetime 对象。

    Returns:
        带 UTC 时区信息的 datetime 对象。
    """
    if val.tzinfo is None:
        # naive datetime 假定为 UTC
        return val.replace(tzinfo=datetime.UTC)
    return val.astimezone(datetime.UTC)


def get_utc_timestamp() -> int:
    return int(datetime.datetime.now(tz=datetime.UTC).timestamp())


def utc_now_naive() -> datetime.datetime:
    """
    获取当前 UTC 时间，不带时区信息（naive datetime），精度到秒。
    """
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0, tzinfo=None)
