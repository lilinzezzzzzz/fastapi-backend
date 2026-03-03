"""加密工具模块

提供统一的加密接口，支持多种加密算法。

使用方式：
    from pkg.crypter import AESCipher, get_crypto_class, EncryptionAlgorithm

    # 直接使用具体实现
    cipher = AESCipher("your-secret-key")
    encrypted = cipher.encrypt("plain text")

    # 或通过工厂函数
    cipher_cls = get_crypto_class(EncryptionAlgorithm.AES)
    cipher = cipher_cls("your-secret-key")
"""

from abc import ABC, abstractmethod
from enum import StrEnum, unique

# =========================================================
# 1. 算法枚举与注册表
# =========================================================


@unique
class EncryptionAlgorithm(StrEnum):
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


# =========================================================
# 2. 抽象基类
# =========================================================


class BaseCryptoUtil(ABC):
    """加密工具抽象基类"""

    def __init__(self, key: str | bytes):
        if not key:
            raise ValueError("Key cannot be empty")
        self.key = key

    @abstractmethod
    def encrypt(self, plain_text: str) -> str:
        """加密"""
        pass

    @abstractmethod
    def decrypt(self, cipher_text: str) -> str:
        """解密"""
        pass


# =========================================================
# 3. 导入具体实现（触发注册）
# =========================================================

from pkg.crypter.aes import AESCipher  # noqa: E402

# =========================================================
# 4. 工厂函数
# =========================================================


def get_crypto_class(algo: EncryptionAlgorithm) -> type[BaseCryptoUtil]:
    """
    根据算法枚举获取对应的加密器类。

    Examples:
        >>> cipher_cls = get_crypto_class(EncryptionAlgorithm.AES)
        >>> cipher = cipher_cls("your-secret-key")
    """
    crypto_class = _ALGORITHM_REGISTRY.get(algo)
    if not crypto_class:
        raise NotImplementedError(
            f"Algorithm '{algo}' is not registered or implemented."
        )

    return crypto_class


__all__ = [
    # 核心接口
    "BaseCryptoUtil",
    "EncryptionAlgorithm",
    "register_algorithm",
    "get_crypto_class",
    # 具体实现
    "AESCipher",
]
