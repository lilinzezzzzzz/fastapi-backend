from internal.config.load_config import setting
from internal.core.logger import logger
from pkg.signature import SignatureAuthHandler

signature_auth_handler: SignatureAuthHandler | None = None


def init_signature_auth_handler():
    global signature_auth_handler

    if signature_auth_handler is not None:
        return

    signature_auth_handler = SignatureAuthHandler(secret_key=setting.JWT_SECRET.get_secret_value())

    logger.info("Signature Auth Handler initialized Successfully.")
