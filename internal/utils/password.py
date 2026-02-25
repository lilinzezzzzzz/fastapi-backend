"""密码加密工具类"""

import bcrypt


class PasswordHandler:
    """
    密码加密与验证工具类

    使用 bcrypt 算法进行密码哈希，具有以下特性：
    - 自动加盐：每次加密都会生成随机盐值
    - 计算成本高：防止暴力破解
    - 不可逆：无法从 hash 还原原始密码
    """

    @staticmethod
    def hash_password(password: str) -> str:
        """
        对密码进行加密

        Args:
            password: 原始密码字符串

        Returns:
            加密后的密码哈希字符串

        Example:
            >>> hashed = PasswordHandler.hash_password("my_password")
            >>> print(hashed)
            '$2b$12$...'
        """
        # 将密码转换为字节
        password_bytes = password.encode("utf-8")

        # 生成盐并加密密码
        salt = bcrypt.gensalt(rounds=12)  # rounds 越大越安全，但计算越慢
        hashed = bcrypt.hashpw(password_bytes, salt)

        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        验证密码是否正确

        Args:
            password: 用户输入的原始密码
            password_hash: 数据库中存储的密码哈希

        Returns:
            bool: 密码正确返回 True，否则返回 False

        Example:
            >>> PasswordHandler.verify_password("my_password", "$2b$12$...")
            True
        """
        try:
            # 将输入转换为字节
            password_bytes = password.encode("utf-8")
            hash_bytes = password_hash.encode("utf-8")

            # bcrypt.checkpw 会自动从 hash 中提取盐值进行验证
            return bcrypt.checkpw(password_bytes, hash_bytes)
        except (ValueError, TypeError) as e:
            # 捕获可能的异常：无效格式、编码错误等
            from pkg.logger import logger
            logger.error(f"Password verification failed: {e}")
            return False

    @staticmethod
    def needs_rehash(password_hash: str) -> bool:
        """
        检查密码哈希是否需要重新加密

        当 bcrypt 算法升级或成本因子增加时，可以检测旧密码是否需要重新加密

        Args:
            password_hash: 当前存储的密码哈希

        Returns:
            bool: 需要重新加密返回 True，否则返回 False
        """
        return bcrypt.hashpw_needs_rehash(password_hash)
