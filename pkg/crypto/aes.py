from cryptography.fernet import Fernet, InvalidToken

from pkg.crypto.base import BaseCryptoUtil, EncryptionAlgorithm, register_algorithm


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


def aes_encrypt(plaintext: str, secret_key: str | bytes) -> str:
    """Convenience function: AES encrypt."""
    return AESCipher(secret_key).encrypt(plaintext)


def aes_decrypt(ciphertext: str, secret_key: str | bytes) -> str:
    """Convenience function: AES decrypt."""
    return AESCipher(secret_key).decrypt(ciphertext)


def aes_generate_key() -> str:
    """Convenience function: Generate AES key."""
    return AESCipher.generate_key()
