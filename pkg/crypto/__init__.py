from abc import ABC, abstractmethod
from enum import Enum, unique
from typing import Literal, overload

from pkg.crypto.aes import AESCipher


@unique
class EncryptionAlgorithm(str, Enum):
    AES = "aes"
    # 将来可以在这里添加 SM4 = "sm4"


_ALGORITHM_REGISTRY: dict[EncryptionAlgorithm, type["BaseCryptoUtil"]] = {}


def register_algorithm(algo: EncryptionAlgorithm):
    """
    装饰器：将加密实现类注册到全局注册表中。
    """

    def decorator(cls):
        _ALGORITHM_REGISTRY[algo] = cls
        return cls

    return decorator


class BaseCryptoUtil(ABC):
    def __init__(self, key: str | bytes):
        if not key:
            raise ValueError("Key cannot be empty")
        self.key = key

    @abstractmethod
    def encrypt(self, plain_text: str) -> str:
        pass

    @abstractmethod
    def decrypt(self, cipher_text: str) -> str:
        pass


@overload
def get_crypto_class(algo: Literal[EncryptionAlgorithm.AES]) -> type[AESCipher]: ...


@overload
def get_crypto_class(algo: EncryptionAlgorithm) -> type[BaseCryptoUtil]: ...


def get_crypto_class(algo: EncryptionAlgorithm) -> type[BaseCryptoUtil]:
    """
    根据算法枚举获取对应的加密器类。
    业务层只需要调用这个函数。
    """
    crypto_class = _ALGORITHM_REGISTRY.get(algo)
    if not crypto_class:
        raise NotImplementedError(
            f"Algorithm '{algo}' is not registered or implemented."
        )

    return crypto_class
