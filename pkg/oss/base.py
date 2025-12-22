from abc import ABC, abstractmethod
from enum import StrEnum
from typing import BinaryIO


class StorageType(StrEnum):
    ALIYUN = "aliyun"
    S3 = "s3"


_STORAGE_REGISTRY: dict[StorageType, type["BaseStorage"]] = {}


def register_storage(storage_type: StorageType):
    """
    装饰器：将存储实现类注册到全局注册表中。
    """

    def decorator(cls):
        _STORAGE_REGISTRY[storage_type] = cls
        return cls

    return decorator


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
