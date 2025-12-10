import datetime


def format_iso_string(val: datetime.datetime, *, use_z: bool = False) -> str:
    """
    将 datetime 对象格式化为 ISO 8601 字符串。
    - 有时区信息：保留时区并输出 ISO 格式
    - 无时区信息：假定为 UTC

    Args:
        val: 要格式化的 datetime 对象。
        use_z: 如果为 True 且时区为 UTC，输出 'Z' 格式；否则输出 '+00:00' 格式。

    Returns:
        ISO 8601 格式的字符串。
    """
    if val.tzinfo is None:
        val = val.replace(tzinfo=datetime.UTC)

    if use_z and val.utcoffset() == datetime.timedelta(0):
        return val.strftime("%Y-%m-%dT%H:%M:%SZ")

    return val.isoformat()


def parse_iso_datetime(iso_string: str) -> datetime.datetime:
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
        return datetime.datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"Invalid ISO format string: {iso_string}") from e


def convert_to_utc_tz(val: datetime.datetime) -> datetime.datetime:
    """
    Args:
        val: 要转换的 datetime 对象。

    Returns:
        带 UTC 时区信息的 datetime 对象。
    """
    return val.astimezone(datetime.timezone.utc)


def get_utc_timestamp() -> int:
    return int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())


def get_utc_without_tzinfo() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0, tzinfo=None)
