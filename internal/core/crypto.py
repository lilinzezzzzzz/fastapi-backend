from pkg.crypto import AESCipher

aes_cipher: AESCipher | None = None


def init_aes_cipher(secret_key: str):
    global aes_cipher
    aes_cipher: AESCipher = AESCipher(secret_key)
