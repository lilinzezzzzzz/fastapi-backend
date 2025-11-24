from starlette.types import ASGIApp, Scope, Receive, Send
from starlette.datastructures import MutableHeaders

from internal.core.auth_token import verify_token
from pkg.signature_tool import signature_auth_helper
from pkg.context_tool import set_user_id_context_var
from pkg.logger_tool import logger
from pkg.resp_tool import response_factory

# 转换成 set 查询更快
auth_token_white = {
    "/auth/login",
    "/auth/register",
    "/docs",
    "/openapi.json",
    "/v1/auth/login_by_account",
    "/v1/auth/login_by_phone",
    "/v1/auth/verify_token"
}


class ASGIAuthMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]

        # 1. 白名单放行
        if path.startswith("/v1/public") or path in auth_token_white or path.startswith("/test"):
            # 某些白名单也可能需要记录日志，可视情况添加
            set_user_id_context_var(0)
            await self.app(scope, receive, send)
            return

        # 使用 MutableHeaders 方便获取头部信息 (类似 dict)
        headers = MutableHeaders(scope=scope)

        # 2. 内部接口签名校验 /v1/internal
        if path.startswith("/v1/internal"):
            x_signature = headers.get("X-Signature")
            x_timestamp = headers.get("X-Timestamp")
            x_nonce = headers.get("X-Nonce")

            if not await signature_auth_helper.verify(signature=x_signature, timestamp=x_timestamp, nonce=x_nonce):
                resp = response_factory.resp_401(
                    msg=f"signature_auth failed, x_signature={x_signature}, x_timestamp={x_timestamp}, x_nonce={x_nonce}"
                )
                # 直接调用 response 对象的 ASGI 接口发送
                await resp(scope, receive, send)
                return

            await self.app(scope, receive, send)
            return

        # 3. Token 校验
        auth_header = headers.get("Authorization", "")

        # 兼容 Bearer Token
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        else:
            token = auth_header

        if not token:
            logger.warning("get empty token from Authorization")
            resp = response_factory.resp_401(message="invalid or missing token")
            await resp(scope, receive, send)
            return

        logger.info(f"verify token: {token}")
        user_data, ok = await verify_token(token)
        if not ok:
            resp = response_factory.resp_401(message="invalid or missing token")
            await resp(scope, receive, send)
            return

        user_id = user_data.get("id")
        if not user_id:
            resp = response_factory.resp_401(message="invalid or missing token, user_id is None")
            await resp(scope, receive, send)
            return

        # 4. 设置上下文 (在 ASGI 中这里是安全的，会传递给 self.app)
        logger.info(f"set user_id to context: {user_id}")
        set_user_id_context_var(user_id)

        await self.app(scope, receive, send)
