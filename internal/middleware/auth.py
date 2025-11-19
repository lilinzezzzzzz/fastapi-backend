from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from internal.core.auth_token import verify_token
from pkg.signature_tool import signature_auth_helper
from pkg.context_tool import set_user_id_context_var
from pkg.logger_tool import logger
from pkg.resp_tool import response_factory

auth_token_white = [
    "/auth/login",
    "/auth/register",
    "/docs",
    "/openapi.json",
    "/v1/auth/login_by_account",
    "/v1/auth/login_by_phone",
    "/v1/auth/verify_token"
]


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        url_path = request.url.path
        if url_path.startswith("/v1/public"):
            return await call_next(request)

        if url_path in auth_token_white or url_path.startswith("/test"):
            logger.info(f"skip auth: {url_path}")
            return await call_next(request)

        if url_path.startswith("/v1/internal"):
            x_signature = request.headers.get("X-Signature")
            x_timestamp = request.headers.get("X-Timestamp")
            x_nonce = request.headers.get("X-Nonce")
            if not await signature_auth_helper.verify(signature=x_signature, timestamp=x_timestamp, nonce=x_nonce):
                return response_factory.resp_401(
                    msg=f"signature_auth failed, x_signature={x_signature}, x_timestamp={x_timestamp}, x_nonce={x_nonce}"
                )
            return await call_next(request)

        # token 校验
        token = request.headers.get("Authorization", "")
        if token == "":
            logger.warning("get empty token from Authorization")
            return response_factory.resp_401(message="invalid or missing token")

        logger.info(f"verify token: {token}")
        user_data, ok = await verify_token(token)
        if not ok:
            return response_factory.resp_401(message="invalid or missing token")

        user_id = user_data.get("id")
        if not user_id:
            return response_factory.resp_401(message="invalid or missing token, user_id is None")

        logger.info(f"set user_id to context: {user_id}")
        set_user_id_context_var(user_id)
        return await call_next(request)