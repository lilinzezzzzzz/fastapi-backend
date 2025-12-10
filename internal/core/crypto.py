from pkg.crypto import AESCipher, EncryptionAlgorithm, get_crypto

aes_cipher: AESCipher = get_crypto(EncryptionAlgorithm.AES)("secret_key")
