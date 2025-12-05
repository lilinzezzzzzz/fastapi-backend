from datetime import timedelta, timezone, datetime

import jwt
from loguru import logger


async def verify_jwt_token(token: str, secret: str, algorithm: str) -> tuple[int | None, bool]:
    """
    验证 Token = request.headers.get("Authorization")
    """
    if not token or not token.startswith("Bearer "):
        return None, False

    token = token.split(" ")[1]
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
        user_id = payload.get("user_id")
        if user_id is None:
            logger.warning("Token verification failed: user_id not found")
            return None, False
    except jwt.ExpiredSignatureError:
        logger.warning("Token verification failed: token expired")
        return None, False
    except jwt.InvalidTokenError:
        logger.warning("Token verification failed: invalid token")
        return None, False

    return user_id, True


def create_jwt_token(user_id: int, username: str, secret: str, expire_minutes: int, algorithm: str):
    expiration = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {
        "username": username,
        "user_id": user_id,
        "exp": int(expiration.timestamp())  # Token 有效期 30 分钟
    }
    return jwt.encode(payload, secret, algorithm=algorithm)
