from pkg.oss.aliyun import AliyunOSSBackend
from pkg.toolkit.types import LazyProxy

_aliyun_oss: AliyunOSSBackend | None = None


def init_aliyun_oss(bucket_name: str, access_key: str, secret_key: str, endpoint: str = None, region: str = None):
    global _aliyun_oss
    _aliyun_oss = AliyunOSSBackend(
        bucket_name=bucket_name, access_key=access_key, secret_key=secret_key, endpoint=endpoint, region=region
    )


def _get_aliyun_oss() -> AliyunOSSBackend:
    if _aliyun_oss is None:
        raise RuntimeError("Aliyun OSS not initialized.")
    return _aliyun_oss


aliyun_oss = LazyProxy(_get_aliyun_oss)
