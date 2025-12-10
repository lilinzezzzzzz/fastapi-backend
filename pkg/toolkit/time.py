import datetime


def datetime_to_string(val: datetime.datetime) -> str:
    """
    格式化 datetime 对象为字符串。
    - 如果有时区信息，保留时区信息并使用 ISO 格式。
    - 如果没有时区信息，假定为 UTC，并格式化为 '2024-12-06T14:12:31Z' 格式。

    Args:
        val (datetime): 要格式化的 datetime 对象。

    Returns:
        str: 格式化后的字符串。
    """
    if val.tzinfo:
        # 有时区信息，保留时区信息并使用 ISO 格式
        return val.isoformat()
    else:
        # 没有时区信息，添加 'Z' 表示 UTC 时间
        return val.replace(tzinfo=datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# 将字符串转换为 datetime 对象
def iso_to_datetime(iso_string: str) -> datetime.datetime:
    """
    将 ISO 格式的时间字符串转换为 datetime 对象。

    :param iso_string: ISO 格式的时间字符串（例如 "2024-12-23T18:30:00Z" 或 "2024-12-23T18:30:00+00:00"）
    :return: 转换后的 datetime 对象
    """
    try:
        # 解析 ISO 格式字符串为 datetime 对象
        dt = datetime.datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt
    except ValueError as e:
        raise ValueError(f"Invalid ISO format string: {iso_string}") from e


def convert_to_utc(val: datetime.datetime) -> datetime.datetime:
    """
    将没有时区信息的东八区时间转换为 UTC 时间

    Args:
        val (datetime): 要转换的 datetime 对象。

    Returns:
        datetime: 转换后的 UTC 时间，且不带时区信息。
    """
    # 如果没有时区信息，假定为东八区时间
    if val.tzinfo is None:
        val = datetime.timezone('Asia/Shanghai').localize(val)

    # 转换为 UTC 时间并移除时区信息
    return val.astimezone(datetime.timezone.utc)


def get_utc_timestamp() -> int:
    return int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())


def get_utc_without_tzinfo() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0, tzinfo=None)


def utc_datetime_with_no_tz() -> datetime.datetime:
    return datetime.datetime.now().replace(tzinfo=None, microsecond=0)


# 把"2024-10-21T12:26:04+08:00"转化成utcdatetime
def parse_datetime_from_str(s: str) -> datetime.datetime | None:
    if not s or s == "0001-01-01T00:00:00Z":
        return None
    # 先把字符串转化成datetime
    dt = datetime.datetime.fromisoformat(s)
    # 再把datetime转化成utcdatetime
    return dt.astimezone(datetime.timezone.utc)


def deep_compare_dict(d1: dict, d2: dict):
    if d1 is None and d2 is None:
        return True

    if d1 is None or d2 is None:
        return False

    if not (isinstance(d1, dict) and isinstance(d2, dict)):
        return False

    if d1.keys() != d2.keys():
        return False

    for key in d1:
        if isinstance(d1[key], dict) and isinstance(d2[key], dict):
            if not deep_compare_dict(d1[key], d2[key]):
                return False
        elif d1[key] != d2[key]:
            return False
    return True
