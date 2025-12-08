from pkg.crypto import EncryptionAlgorithm, crypto_factory

aes_cipher = crypto_factory(EncryptionAlgorithm.AES)("secret_key")
