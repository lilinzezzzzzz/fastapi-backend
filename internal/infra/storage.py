from pkg.oss.aliyun import AliyunOSSBackend

aliyun_oss: AliyunOSSBackend | None = None


def init_aliyun_oss(bucket_name: str, access_key: str, secret_key: str, endpoint: str = None, region: str = None):
    global aliyun_oss
    aliyun_oss = AliyunOSSBackend(
        bucket_name=bucket_name, access_key=access_key, secret_key=secret_key, endpoint=endpoint, region=region
    )
