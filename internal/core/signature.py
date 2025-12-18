from internal.config.load_config import setting
from internal.core.logger import logger
from pkg.signature import SignatureAuthHandler

_signature_auth_handler: SignatureAuthHandler | None = None


def init_signature_auth_handler():
    global _signature_auth_handler

    if _signature_auth_handler is not None:
        return

    _signature_auth_handler = SignatureAuthHandler(secret_key=setting.JWT_SECRET.get_secret_value())

    logger.info("Signature Auth Handler initialized Successfully.")
