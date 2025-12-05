import bcrypt


def hash_password(password: str) -> str:
    """
    对密码进行哈希加密。
    """
    # 生成盐
    salt = bcrypt.gensalt()
    # 哈希密码
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码是否匹配。
    """
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
