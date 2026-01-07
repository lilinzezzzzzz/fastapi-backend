from typing import overload

# 再导入具体实现（会触发 @register_algorithm 装饰器注册）
from pkg.crypter.aes import AESCipher
# 先导入基础类（无循环依赖）
from pkg.crypter.base import (BaseCryptoUtil, EncryptionAlgorithm, _ALGORITHM_REGISTRY, register_algorithm)


@overload
def get_crypto_class(algo: EncryptionAlgorithm.AES) -> type[AESCipher]: ...


@overload
def get_crypto_class(algo: EncryptionAlgorithm) -> type[BaseCryptoUtil]: ...


def get_crypto_class(algo: EncryptionAlgorithm) -> type[BaseCryptoUtil]:
    """
    根据算法枚举获取对应的加密器类。
    业务层只需要调用这个函数。
    """
    crypto_class = _ALGORITHM_REGISTRY.get(algo)
    if not crypto_class:
        raise NotImplementedError(
            f"Algorithm '{algo}' is not registered or implemented."
        )

    return crypto_class
