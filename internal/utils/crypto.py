from pkg.crypter import AESCipher
from pkg.toolkit.types import LazyProxy

_aes_cipher: AESCipher | None = None


def init_aes_cipher(secret_key: str):
    global _aes_cipher
    _aes_cipher = AESCipher(secret_key)


def _get_aes_cipher() -> AESCipher:
    if _aes_cipher is None:
        raise RuntimeError("AES Cipher is not initialized")
    return _aes_cipher


aes_cipher = LazyProxy[AESCipher](_get_aes_cipher)
