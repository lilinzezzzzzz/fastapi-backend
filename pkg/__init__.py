import datetime
import hashlib
import os
import random
import re
import string
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlunparse
from string import Template
import orjson
import pytz
import shortuuid
import xxhash


def get_base_dir() -> Path:
    """
    获取项目根目录的路径。

    :return: 项目根目录的路径
    """
    return Path(__file__).parent.parent.absolute()


def get_sys_env() -> str:
    return str.lower(os.getenv("APP_ENV", "unknown"))


def get_sys_namespace() -> str:
    if SYS_ENV == "local":
        namespace = "dev"
    elif SYS_ENV == "local_test":
        namespace = "test"
    else:
        namespace = SYS_ENV
    return namespace


def orjson_dumps(*args, **kwargs):
    return orjson.dumps(*args, **kwargs).decode("utf-8")


def orjson_loads(*args, **kwargs):
    return orjson.loads(*args, **kwargs)


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
        return val.replace(tzinfo=pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        val = pytz.timezone('Asia/Shanghai').localize(val)

    # 转换为 UTC 时间并移除时区信息
    return val.astimezone(pytz.utc)


def hash_to_int(data: str) -> int:
    return xxhash.xxh64_intdigest(data)


def extract_dict(d, keys):
    return {k: v for k, v in d.items() if k in keys}


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


def unique_string_w_timestamp() -> str:
    """
    使用时间戳和随机数生成唯一字符串。
    """
    timestamp = str(int(time.time() * 1e6))  # 精确到微秒的时间戳
    random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    return timestamp + random_part


def deep_compare_dict(d1, d2):
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


def token_cache_key(token: str) -> str:
    return f"token:{token}"


def token_list_cache_key(user_id: int) -> str:
    return f"token_list:{user_id}"


# 生成唯一的文件名
def generate_unique_filename(filename: str) -> str:
    return f"{uuid.uuid4().hex}_{filename}"


def create_uuid_token():
    return shortuuid.uuid()


def validate_phone_number(phone: str) -> bool:
    """
    校验手机号是否符合中国大陆的手机号格式
    :param phone: 待验证的手机号字符串
    :return: 如果手机号格式正确，返回 True，否则返回 False
    """
    # 正则表达式：以1开头，第二位是3-9之间的数字，后面是9个数字
    pattern = r"^1[3-9]\d{9}$"

    if re.match(pattern, phone):
        return True
    else:
        return False


def generate_account_by_phone(phone_number: str) -> str:
    # 选择哈希算法（例如 SHA-256）
    hashed_phone = hashlib.sha256(phone_number.encode('utf-8')).hexdigest()

    # 为了增加唯一性，也可以使用 UUID 来保证生成的 ID 是唯一的
    unique_account_id = f"user_{hashed_phone}"

    return unique_account_id


def build_url(
        scheme: str = "http",
        netloc: str = "localhost",
        path: str = "/",
        query: dict | None = None,  # 仅支持字典或 None
        fragment: str = ""
):
    """
    构建一个 URL，使用默认值填充缺失的部分。

    :param scheme: URL 协议（默认为 "http"）
    :param netloc: 网络位置（默认为 "localhost"）
    :param path: 资源路径（默认为 "/"）
    :param query: 查询字符串，必须是字典类型或 None（默认为 None）
    :param fragment: 片段标识符（默认为 ""）
    :return: 组装后的完整 URL

    示例：
    >>> build_url(scheme="https", path="api", query={"page": 2, "sort": "desc"})
    'https://localhost/api?page=2&sort=desc'

    >>> build_url(path="search", query={"q": "python"})
    'http://localhost/search?q=python'

    >>> build_url(path="profile")
    'http://localhost/profile'
    """
    # 处理 path，确保以 `/` 开头
    path = "/" + path.lstrip("/") if path else "/"

    # 处理 query（如果是字典，转换为 URL 编码字符串）
    if query is None:
        query_string = ""
    elif isinstance(query, dict):
        query_string = urlencode(query)
    else:
        raise ValueError("query must be none or dict")

    # 根据 scheme 设定默认 netloc
    if not netloc:
        netloc = "localhost:443" if scheme == "https" else "localhost:80"

    # 组装 URL（去掉 params 参数）
    return urlunparse((scheme, netloc, path, "", query_string, fragment))


def template_substitute(template: Template | str, safe: bool = False, **kwargs) -> str:
    """
    使用字符串模板替换变量。

    :param template: 字符串模板，包含变量占位符
    :param kwargs: 替换变量的字典
    :param safe: 是否使用安全模式
    :return: 替换后的字符串
    
    使用示例：
        >>> result = template_substitute(Template("Hello {name}, you are {age} years old"), name="Alice", age=25)
        >>> print(result)
        Hello Alice, you are 25 years old
    """
    if isinstance(template, str):
        template = Template(template)

    if safe:
        return template.safe_substitute(**kwargs)

    return template.substitute(**kwargs)


BASE_DIR: Path = get_base_dir()
SYS_ENV: str = get_sys_env()
SYS_NAMESPACE: str = get_sys_namespace()
