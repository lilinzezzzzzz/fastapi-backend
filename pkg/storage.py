import asyncio
import io
from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Literal, overload

import boto3
import oss2
from botocore.exceptions import ClientError


# ==========================================
# 1. 定义存储类型枚举
# ==========================================


class StorageType(StrEnum):
    ALIYUN = "aliyun"
    S3 = "s3"


# ==========================================
# 2. 全局注册表 (Registry)
# ==========================================

# 用于存储 存储类型枚举 -> 实现类 的映射
_STORAGE_REGISTRY: dict[StorageType, type["BaseStorage"]] = {}


def register_storage(storage_type: StorageType):
    """
    装饰器：将存储实现类注册到全局注册表中。
    """

    def decorator(cls):
        _STORAGE_REGISTRY[storage_type] = cls
        return cls

    return decorator


# ==========================================
# 3. 策略接口 (Base Class)
# ==========================================


class BaseStorage(ABC):
    @abstractmethod
    async def upload(self, file_obj: BinaryIO | bytes | str, path: str, content_type: str = None) -> str:
        pass

    @abstractmethod
    async def generate_presigned_url(self, path: str, expiration: int = 3600) -> str:
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        pass


# ==========================================
# 4. 具体实现 (Implementation)
# ==========================================


@register_storage(StorageType.ALIYUN)
class AliyunOSSBackend(BaseStorage):
    """
    阿里云 OSS 存储后端实现。
    已自动注册到 _STORAGE_REGISTRY。
    """

    def __init__(self, *, bucket_name: str, access_key: str, secret_key: str, endpoint: str = None, region: str = None):
        if not access_key or not secret_key:
            raise ValueError("Aliyun OSS requires access_key and secret_key")

        auth = oss2.Auth(access_key, secret_key)
        # 阿里云 endpoint 处理逻辑
        real_endpoint = endpoint if endpoint else f"oss-{region}.aliyuncs.com"
        # 确保 protocol 存在 (oss2 需要 http:// 或 https://)
        if not real_endpoint.startswith("http"):
            real_endpoint = f"https://{real_endpoint}"

        self.bucket = oss2.Bucket(auth, real_endpoint, bucket_name)

    async def upload(self, file_obj, path: str, content_type: str = None) -> str:
        headers = {'Content-Type': content_type} if content_type else None

        def _sync_upload():
            try:
                # 1. 路径上传
                if isinstance(file_obj, (str, Path)):
                    self.bucket.put_object_from_file(path, str(file_obj), headers=headers)
                # 2. Bytes 上传
                elif isinstance(file_obj, bytes):
                    self.bucket.put_object(path, file_obj, headers=headers)
                # 3. FastAPI UploadFile 或 文件对象
                else:
                    # 兼容 FastAPI UploadFile
                    real_file = file_obj.file if hasattr(file_obj, "file") else file_obj

                    if hasattr(real_file, 'seek'):
                        real_file.seek(0)

                    self.bucket.put_object(path, real_file, headers=headers)

            except oss2.exceptions.OssError as e:
                raise Exception(f"Aliyun OSS Upload failed: {e}") from e

        await asyncio.to_thread(_sync_upload)
        # 阿里云签名 URL (或根据需求直接拼接 CDN 域名)
        return await asyncio.to_thread(self.bucket.sign_url, 'GET', path, 3600)

    async def generate_presigned_url(self, path: str, expiration: int = 3600) -> str:
        return await asyncio.to_thread(self.bucket.sign_url, 'GET', path, expiration)

    async def delete(self, path: str) -> bool:
        result = await asyncio.to_thread(self.bucket.delete_object, path)
        return result.status == 204

    async def exists(self, path: str) -> bool:
        return await asyncio.to_thread(self.bucket.object_exists, path)


@register_storage(StorageType.S3)
class S3Backend(BaseStorage):
    """
    AWS S3 / S3 兼容存储后端实现。
    已自动注册到 _STORAGE_REGISTRY。
    """

    def __init__(self, bucket_name: str, access_key: str, secret_key: str, endpoint: str = None, region: str = None):
        self.bucket_name = bucket_name
        self.endpoint = endpoint
        self.client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            endpoint_url=endpoint
        )

    async def upload(self, file_obj, path: str, content_type: str = None) -> str:
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type

        def _sync_upload():
            try:
                # 1. 路径上传
                if isinstance(file_obj, (str, Path)):
                    self.client.upload_file(str(file_obj), self.bucket_name, path, ExtraArgs=extra_args)

                # 2. Bytes / 文件对象
                else:
                    # 兼容 FastAPI UploadFile
                    real_file = file_obj.file if hasattr(file_obj, "file") else file_obj

                    if isinstance(real_file, bytes):
                        # Boto3 upload_fileobj 需要 file-like object，所以这里要把 bytes 包装
                        data_stream = io.BytesIO(real_file)
                    else:
                        data_stream = real_file
                        if hasattr(data_stream, 'seek'):
                            data_stream.seek(0)

                    self.client.upload_fileobj(data_stream, self.bucket_name, path, ExtraArgs=extra_args)

            except ClientError as e:
                raise Exception(f"S3 Upload failed: {str(e)}") from e

        await asyncio.to_thread(_sync_upload)

        # 返回逻辑
        if self.endpoint:
            return f"{self.endpoint}/{self.bucket_name}/{path}"
        return f"https://{self.bucket_name}.s3.amazonaws.com/{path}"

    async def generate_presigned_url(self, path: str, expiration: int = 3600) -> str:
        def _gen():
            return self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': path},
                ExpiresIn=expiration
            )

        return await asyncio.to_thread(_gen)

    async def delete(self, path: str) -> bool:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket_name, Key=path)
        return True

    async def exists(self, path: str) -> bool:
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=self.bucket_name, Key=path)
            return True
        except ClientError:
            return False


# ==========================================
# 5. 公共入口函数 (Factory Function)
# ==========================================


@overload
def get_storage_class(storage_type: Literal[StorageType.ALIYUN]) -> type[AliyunOSSBackend]: ...


@overload
def get_storage_class(storage_type: Literal[StorageType.S3]) -> type[S3Backend]: ...


def get_storage_class(storage_type: StorageType) -> type[BaseStorage]:
    """
    根据存储类型枚举获取对应的存储后端类。
    业务层只需要调用这个函数。
    """
    storage_class = _STORAGE_REGISTRY.get(storage_type)
    if not storage_class:
        raise NotImplementedError(
            f"Storage type '{storage_type}' is not registered or implemented."
        )
    return storage_class
