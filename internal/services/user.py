from internal.dao.user import UserDao, user_dao
from internal.models.user import User
from internal.utils.password import PasswordHandler


class UserService:
    def __init__(self, dao: UserDao):
        self._user_dao = dao

    @staticmethod
    async def hello_world():
        return "Hello World"

    async def get_user_by_phone(self, phone: str) -> User | None:
        # 建议直接传参数，而不是传 request 对象，这样 Service 更纯粹，更容易测试
        return await self._user_dao.get_by_phone(phone)

    async def get_user_by_username(self, username: str) -> User | None:
        """根据用户名查询用户"""
        return await self._user_dao.get_by_username(username)

    async def verify_password(self, user: User, password: str) -> bool:
        """
        验证用户密码

        Args:
            user: 用户对象
            password: 待验证的密码

        Returns:
            bool: 密码正确返回 True，否则返回 False
        """
        if not user.password_hash:
            return False

        return PasswordHandler.verify_password(password, user.password_hash)

    async def create_user(self, username: str, account: str, phone: str, password: str) -> User:
        """
        创建新用户（带密码加密）

        Args:
            username: 用户名
            account: 账号
            phone: 手机号
            password: 原始密码

        Returns:
            User: 创建的用户对象
        """
        # 检查手机号是否已存在
        if await self._user_dao.is_phone_exist(phone):
            raise ValueError(f"手机号 {phone} 已被注册")

        # 加密密码
        password_hash = PasswordHandler.hash_password(password)

        # 创建用户
        user = await self._user_dao.create(
            username=username,
            account=account,
            phone=phone,
            password_hash=password_hash,
        )

        return user


def new_user_service() -> UserService:
    """
    依赖注入工厂函数，创建 UserService 实例。

    注意：每次调用都会创建新实例，由 FastAPI 管理生命周期（默认每个请求一个实例）。
    DAO 使用全局单例 user_dao。
    """
    return UserService(user_dao)
