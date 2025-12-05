import anyio
import bcrypt


class PasswordHasher:
    def __init__(self, rounds: int = 12):
        self.rounds = rounds

    def _hash_sync(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=self.rounds)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def _verify_sync(plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    async def hash(self, password: str) -> str:
        if not password:
            raise ValueError("Password cannot be empty")
        return await anyio.to_thread.run_sync(self._hash_sync, password)

    async def verify(self, plain_password: str, hashed_password: str) -> bool:
        if not plain_password or not hashed_password:
            return False
        return await anyio.to_thread.run_sync(self._verify_sync, plain_password, hashed_password)


"""
from pkg.bcrypt import password_hasher

# 哈希密码
hashed = await password_hasher.hash("my_password")

# 验证密码
is_valid = await password_hasher.verify("my_password", hashed)

# 自定义 rounds
custom_hasher = PasswordHasher(rounds=14)
"""
