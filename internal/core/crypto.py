from pkg.crypto import AESCipher, EncryptionAlgorithm, crypto_factory

aes_cipher: AESCipher = crypto_factory(EncryptionAlgorithm.AES)("secret_key")
