from internal.config.setting import setting
from pkg.signature import SignatureAuthHandler

signature_auth_handler: SignatureAuthHandler | None = None


async def init_signature_auth_handler():
    global signature_auth_handler

    if signature_auth_handler is not None:
        return

    signature_auth_handler = SignatureAuthHandler(
        secret_key=setting.SECRET_KEY
    )
