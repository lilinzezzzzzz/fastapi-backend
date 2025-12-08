from abc import ABC, abstractmethod
from enum import Enum, unique

import anyio
import bcrypt
from cryptography.fernet import Fernet, InvalidToken

# =========================================================
# Encryption Algorithms Enum
# =========================================================


@unique
class EncryptionAlgorithm(str, Enum):
    AES = "aes"


# =========================================================
# Strategy Interface
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
# AES Implementation (Fernet)
# =========================================================


class AESCipher(BaseCryptoUtil):
    """
    基于 Fernet 的 AES 加密实现。
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
        """
        生成一个随机的、符合 Fernet 标准的密钥。
        通常用于项目初始化或生成配置文件。

        Returns:
            str: URL-safe Base64 编码的密钥字符串 (可以直接写入 YAML/Env)
        """
        # Fernet.generate_key() 返回 bytes，我们需要 decode 成 str 以便存入配置文件
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
# Factory
# =========================================================


class CryptoFactory:
    _MAPPING: dict[EncryptionAlgorithm, type[BaseCryptoUtil]] = {
        EncryptionAlgorithm.AES: AESCipher,
    }

    @staticmethod
    def get_crypto_util(algo: EncryptionAlgorithm, key: str | bytes) -> BaseCryptoUtil:
        crypto_class = CryptoFactory._MAPPING.get(algo)
        if not crypto_class:
            raise NotImplementedError(f"Algorithm {algo} is not implemented yet.")
        return crypto_class(key)


crypto_factory = CryptoFactory()

# =========================================================
# Helpers
# =========================================================


def aes_encrypt(plaintext: str, secret_key: str | bytes) -> str:
    return AESCipher(secret_key).encrypt(plaintext)


def aes_decrypt(ciphertext: str, secret_key: str | bytes) -> str:
    return AESCipher(secret_key).decrypt(ciphertext)


# =========================================================
# Password Hasher
# =========================================================


class PasswordHasher:
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

# =========================================================
# CLI Utility (方便你在命令行直接生成 Key)
# =========================================================

if __name__ == "__main__":
    print("--- AES Key Generator ---")
    new_key = AESCipher.generate_key()
    print(f"Generated Key: {new_key}")
    print("Copy the above key into your config.yaml or .env file.")
