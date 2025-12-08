import base64
from abc import ABC, abstractmethod
from enum import Enum, unique

import anyio
import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# =========================================================
# Encryption Algorithms Enum
# =========================================================


@unique
class EncryptionAlgorithm(str, Enum):
    SM4_ECB = "sm4_ecb_no_iv"
    SM4_CBC = "sm4_cbc_with_iv"
    AES = "aes"  # 使用 Fernet (AES-128-CBC + HMAC)


# =========================================================
# Strategy Interface
# =========================================================


class BaseCryptoUtil(ABC):
    """
    加密工具抽象基类 (Strategy Interface)。
    """

    def __init__(self, key: str | bytes):
        """
        初始化加密器。
        :param key: 算法所需的密钥（格式由具体子类决定，如 Hex 或 Base64）
        """
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
# Helper: Key Derivation (PBKDF2)
# =========================================================


def derive_key_from_password(password: str, salt: bytes | str | None = None) -> bytes:
    """
    从密码派生密钥 (PBKDF2HMAC)。
    这是一个耗时操作，建议缓存结果或在应用启动时执行一次。

    Returns:
        Fernet URL-safe Base64 encoded key
    """
    _DEFAULT_SALT = b"fastapi_aes_salt_default"

    if salt is None:
        salt_bytes = _DEFAULT_SALT
    elif isinstance(salt, str):
        salt_bytes = salt.encode("utf-8")
    else:
        salt_bytes = salt

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt_bytes,
        iterations=100_000,
    )
    # Fernet 需要 URLSafe Base64 编码的 32 字节密钥
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


# =========================================================
# AES Implementation (Fernet)
# =========================================================


class AESCipher(BaseCryptoUtil):
    """
    基于 Fernet 的 AES 加密实现。

    注意：此类现在只负责加密/解密，不再负责从密码派生密钥。
    这大大提高了多次调用时的性能。
    """

    def __init__(self, key: str | bytes):
        super().__init__(key)
        try:
            # 确保 key 是 bytes 格式
            ensure_bytes_key = key if isinstance(key, bytes) else key.encode("utf-8")
            self._fernet = Fernet(ensure_bytes_key)
        except Exception as e:
            raise ValueError(f"Invalid AES/Fernet key provided: {e}")

    def encrypt(self, plain_text: str) -> str:
        """
        加密字符串。
        """
        if not plain_text:
            return ""
        encrypted_bytes = self._fernet.encrypt(plain_text.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, cipher_text: str) -> str:
        """
        解密字符串。
        """
        if not cipher_text:
            return ""
        try:
            decrypted_bytes = self._fernet.decrypt(cipher_text.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            raise ValueError("Decryption failed: Invalid token or wrong key")


# =========================================================
# Factory
# =========================================================


class CryptoFactory:
    """
    加密工厂类。
    """

    _MAPPING: dict[EncryptionAlgorithm, type[BaseCryptoUtil]] = {
        EncryptionAlgorithm.AES: AESCipher,
    }

    @staticmethod
    def get_crypto_util(algo: EncryptionAlgorithm, key: str | bytes) -> BaseCryptoUtil:
        """
        获取加密工具实例。

        :param algo: 算法枚举
        :param key: 适用于该算法的密钥
        """
        crypto_class = CryptoFactory._MAPPING.get(algo)
        if not crypto_class:
            raise NotImplementedError(f"Algorithm {algo} is not implemented yet.")

        return crypto_class(key)


# 全局单例工厂（如果不需要状态，其实直接用静态方法即可）
crypto_factory = CryptoFactory()


# =========================================================
# 便捷函数 (为了兼容旧代码调用方式，但增加了优化)
# =========================================================


def aes_encrypt(
    plaintext: str, secret_key: str, salt: bytes | str | None = None
) -> str:
    """
    **注意**：此函数每次调用都会进行 PBKDF2 运算（慢）。
    生产环境建议在外部生成好 key，直接调用 AESCipher(key).encrypt()。
    """
    real_key = derive_key_from_password(secret_key, salt)
    return AESCipher(real_key).encrypt(plaintext)


def aes_decrypt(
    ciphertext: str, secret_key: str, salt: bytes | str | None = None
) -> str:
    real_key = derive_key_from_password(secret_key, salt)
    return AESCipher(real_key).decrypt(ciphertext)


# =========================================================
# Password Hasher (Bcrypt)
# =========================================================


class PasswordHasher:
    """
    密码哈希工具 (Bcrypt)。
    """

    def __init__(self, rounds: int = 12):
        self.rounds = rounds

    def _hash_sync(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=self.rounds)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def _verify_sync(plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"), hashed_password.encode("utf-8")
            )
        except (ValueError, TypeError):
            return False

    async def hash(self, password: str) -> str:
        if not password:
            raise ValueError("Password cannot be empty")
        return await anyio.to_thread.run_sync(self._hash_sync, password)

    async def verify(self, plain_password: str, hashed_password: str) -> bool:
        if not plain_password or not hashed_password:
            return False
        return await anyio.to_thread.run_sync(
            self._verify_sync, plain_password, hashed_password
        )


password_hasher = PasswordHasher()
