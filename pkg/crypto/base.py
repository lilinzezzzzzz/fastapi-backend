from abc import ABC, abstractmethod
from enum import Enum, unique


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
