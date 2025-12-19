from internal.config.load_config import settings
from internal.core.logger import logger
from pkg.signature import SignatureAuthHandler
from pkg.toolkit.types import LazyProxy

_signature_auth_handler: SignatureAuthHandler | None = None


def init_signature_auth_handler():
    global _signature_auth_handler

    if _signature_auth_handler is not None:
        return

    _signature_auth_handler = SignatureAuthHandler(secret_key=settings.JWT_SECRET.get_secret_value())

    logger.info("Signature Auth Handler initialized Successfully.")


def get_signature_auth_handler() -> SignatureAuthHandler:
    if _signature_auth_handler is None:
        raise RuntimeError("Signature Auth Handler not initialized. Call init_signature_auth_handler() first.")
    return _signature_auth_handler


signature_auth_handler = LazyProxy(get_signature_auth_handler)
