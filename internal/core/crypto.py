from pkg.crypto import AESCipher, BaseCryptoUtil, EncryptionAlgorithm


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
