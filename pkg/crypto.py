from abc import ABC, abstractmethod
from enum import Enum, unique
from typing import Literal, overload

from cryptography.fernet import Fernet, InvalidToken


# =========================================================
# 1. 定义算法枚举
# =========================================================


@unique
class EncryptionAlgorithm(str, Enum):
    AES = "aes"
    # 将来可以在这里添加 SM4 = "sm4"


# =========================================================
# 2. 全局注册表 (Registry)
# =========================================================

# 用于存储 算法枚举 -> 实现类 的映射
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
# 3. 策略接口 (Base Class)
# =========================================================


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


# =========================================================
# 4. 具体实现 (Implementation)
# =========================================================


@register_algorithm(EncryptionAlgorithm.AES)
class AESCipher(BaseCryptoUtil):
    """
    基于 Fernet 的 AES 加密实现。
    已自动注册到 _ALGORITHM_REGISTRY。
    """

    def __init__(self, key: str | bytes):
        super().__init__(key)
        try:
            # 兼容 str (YAML/JSON 配置) 和 bytes
            ensure_bytes_key = key if isinstance(key, bytes) else key.encode("utf-8")
            self._fernet = Fernet(ensure_bytes_key)
        except Exception as e:
            raise ValueError(
                f"Invalid AES key. Key must be 32 url-safe base64-encoded bytes.\n"
                f"Original error: {e}\n"
                f"Tip: You can use AESCipher.generate_key() to get a valid key."
            )

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode("utf-8")

    def encrypt(self, plain_text: str) -> str:
        if not plain_text:
            return ""
        encrypted_bytes = self._fernet.encrypt(plain_text.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, cipher_text: str) -> str:
        if not cipher_text:
            return ""
        try:
            decrypted_bytes = self._fernet.decrypt(cipher_text.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            raise ValueError("Decryption failed: Invalid token or wrong key")


# =========================================================
# 5. 公共入口函数 (Factory Function)
# =========================================================


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


# =========================================================
# Helpers
# =========================================================


def aes_encrypt(plaintext: str, secret_key: str | bytes) -> str:
    """Convenience function: AES encrypt."""
    crypto_class: type[AESCipher] = get_crypto_class(EncryptionAlgorithm.AES)
    return crypto_class(secret_key).encrypt(plaintext)


def aes_decrypt(ciphertext: str, secret_key: str | bytes) -> str:
    """Convenience function: AES decrypt."""
    crypto_class: type[AESCipher] = get_crypto_class(EncryptionAlgorithm.AES)
    return crypto_class(secret_key).decrypt(ciphertext)


def aes_generate_key() -> str:
    """Convenience function: Generate AES key."""
    crypto_class: type[AESCipher] = get_crypto_class(EncryptionAlgorithm.AES)
    return crypto_class.generate_key()


# =========================================================
# CLI Utility
# =========================================================

if __name__ == "__main__":
    print("--- AES Key Generator ---")
    new_key = AESCipher.generate_key()
    print(f"Generated Key: {new_key}")
