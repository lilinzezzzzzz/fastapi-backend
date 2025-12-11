import random
import re
import string
import time
import uuid
from string import Template
from urllib.parse import urlencode, urlunparse

import xxhash


def unique_string_w_timestamp() -> str:
    """
    使用时间戳和随机数生成唯一字符串。
    """
    timestamp = str(int(time.time() * 1e6))  # 精确到微秒的时间戳
    random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    return timestamp + random_part


def hash_to_int(data: str) -> int:
    return xxhash.xxh64_intdigest(data)


# 生成唯一的文件名
def generate_unique_filename(filename: str) -> str:
    return f"{uuid.uuid4().hex}_{filename}"


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


def generate_unique_int_id():
    """
    使用 UUIDv7 标准 (uuid6.uuid7) 生成一个 64 位的通用、时间排序的整数 ID。

    UUIDv7 确保了 ID 的时间可排序性，这在数据库索引中非常有用。
    该函数返回的是 128 位 UUID 的高 64 位。

    返回值:
        int: 生成的 64 位整数 ID (时间排序)。
    """
    # 1. 生成一个 128 位的 UUIDv7 对象
    # 2. .int 获取其 128 位整数表示
    # 3. >> 64 取高 64 位作为 ID，因为 UUIDv7 的时间戳信息主要集中在高位
    unique_id = uuid6.uuid7().int >> 64
    return unique_id
