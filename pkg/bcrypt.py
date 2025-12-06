import base64

import anyio
import bcrypt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# =========================================================
# AES 加密/解密（基于 Fernet，底层使用 AES-128-CBC）
# =========================================================

class AESCipher:
    """
    AES 加密/解密工具类。

    使用 Fernet 实现，底层基于 AES-128-CBC + HMAC 认证。
    支持使用任意长度的密钥（通过 PBKDF2 派生）。
    """

    # 默认 salt
    _DEFAULT_SALT = b"fastapi_aes_salt"

    def __init__(self, secret_key: str, salt: bytes | str | None = None):
        """
        初始化 AES 加密器。

        Args:
            secret_key: 加密密钥，可以是任意长度的字符串
            salt: 盐值，用于密钥派生。支持 bytes 或 str，不传则使用默认值
        """
        # 处理 salt 参数
        if salt is None:
            salt_bytes = self._DEFAULT_SALT
        elif isinstance(salt, str):
            salt_bytes = salt.encode("utf-8")
        else:
            salt_bytes = salt

        # 使用 PBKDF2 从密钥派生出 Fernet 所需的 32 字节密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt_bytes,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode("utf-8")))
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """
        加密明文。

        Args:
            plaintext: 要加密的明文字符串

        Returns:
            加密后的 Base64 编码字符串
        """
        encrypted = self._fernet.encrypt(plaintext.encode("utf-8"))
        return encrypted.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """
        解密密文。

        Args:
            ciphertext: 加密后的 Base64 编码字符串

        Returns:
            解密后的明文字符串

        Raises:
            InvalidToken: 解密失败（密钥错误或数据被篡改）
        """
        decrypted = self._fernet.decrypt(ciphertext.encode("utf-8"))
        return decrypted.decode("utf-8")


def aes_encrypt(plaintext: str, secret_key: str, salt: bytes | str | None = None) -> str:
    """
    便捷函数：AES 加密。

    Args:
        plaintext: 要加密的明文字符串
        secret_key: 加密密钥
        salt: 盐值，不传则使用默认值

    Returns:
        加密后的 Base64 编码字符串
    """
    return AESCipher(secret_key, salt).encrypt(plaintext)


def aes_decrypt(ciphertext: str, secret_key: str, salt: bytes | str | None = None) -> str:
    """
    便捷函数：AES 解密。

    Args:
        ciphertext: 加密后的 Base64 编码字符串
        secret_key: 解密密钥
        salt: 盐值，必须与加密时使用的盐值一致

    Returns:
        解密后的明文字符串
    """
    return AESCipher(secret_key, salt).decrypt(ciphertext)


# =========================================================
# 密码哈希（bcrypt）
# =========================================================


class PasswordHasher:
    def __init__(self, rounds: int = 12):
        self.rounds = rounds

    def _hash_sync(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=self.rounds)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def _verify_sync(plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    async def hash(self, password: str) -> str:
        if not password:
            raise ValueError("Password cannot be empty")
        return await anyio.to_thread.run_sync(self._hash_sync, password)

    async def verify(self, plain_password: str, hashed_password: str) -> bool:
        if not plain_password or not hashed_password:
            return False
        return await anyio.to_thread.run_sync(self._verify_sync, plain_password, hashed_password)


"""
from pkg.bcrypt import password_hasher

# 哈希密码
hashed = await password_hasher.hash("my_password")

# 验证密码
is_valid = await password_hasher.verify("my_password", hashed)

# 自定义 rounds
custom_hasher = PasswordHasher(rounds=14)
"""
