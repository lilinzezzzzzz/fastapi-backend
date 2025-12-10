from pkg.crypto import AESCipher, EncryptionAlgorithm, get_crypto

aes_cipher: AESCipher | None = None


def init_aes_cipher(secret_key: str):
    global aes_cipher
    aes_cipher: AESCipher = get_crypto(EncryptionAlgorithm.AES)(secret_key)
