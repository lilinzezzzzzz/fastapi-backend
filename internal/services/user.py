from internal.dao.user import UserDao, user_dao
from internal.models.user import User
from internal.utils.password import PasswordHandler
from internal.utils.third_party_auth.base import ThirdPartyUserInfo


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


async def get_or_create_user_by_third_party(
    self,
    platform: str,
    third_party_info: ThirdPartyUserInfo
) -> User:
    """
    根据第三方用户信息获取或创建用户

    Args:
        platform: 平台名称 (wechat, alipay 等)
        third_party_info: 第三方用户信息

    Returns:
        User: 用户对象
    """
    # 根据平台查询对应的唯一标识
    if platform == "wechat":
        existing_user = await self._user_dao.get_by_wechat_openid(third_party_info.open_id)
    elif platform == "alipay":
        existing_user = await self._user_dao.get_by_alipay_user_id(third_party_info.open_id)
    else:
        raise ValueError(f"Unsupported third-party platform: {platform}")

    # 如果用户已存在，直接返回
    if existing_user:
        return existing_user

    # 否则创建新用户
    username = third_party_info.nickname or f"{platform}_{third_party_info.open_id[:8]}"

    # 构建用户数据
    user_data = {
        "username": username,
        "account": f"{platform}_{third_party_info.open_id}",
        "phone": "",  # 第三方登录默认无手机号，需要后续绑定
        "password_hash": None,  # 无密码
    }

    # 根据平台设置对应字段
    if platform == "wechat":
        user_data.update({
            "wechat_openid": third_party_info.open_id,
            "wechat_unionid": third_party_info.union_id,
            "wechat_avatar": third_party_info.avatar,
            "wechat_nickname": third_party_info.nickname,
        })
    elif platform == "alipay":
        user_data.update({
            "alipay_user_id": third_party_info.open_id,
            "alipay_avatar": third_party_info.avatar,
            "alipay_nickname": third_party_info.nickname,
        })

    # 创建用户
    user = await self._user_dao.create(**user_data)

    return user


async def bind_third_party_account(
    self,
    user: User,
    platform: str,
    third_party_info: ThirdPartyUserInfo
) -> None:
    """
    将第三方账号绑定到现有用户

    Args:
        user: 现有用户对象
        platform: 平台名称
        third_party_info: 第三方用户信息

    Raises:
        ValueError: 当该第三方账号已被其他用户绑定时
    """
    # 检查该第三方账号是否已被绑定
    if platform == "wechat":
        if await self._user_dao.is_wechat_openid_exist(third_party_info.open_id):
            raise ValueError("该微信账号已被其他账号绑定")

        # 更新用户信息
        await self._user_dao.update(
            user.id,
            wechat_openid=third_party_info.open_id,
            wechat_unionid=third_party_info.union_id,
            wechat_avatar=third_party_info.avatar,
            wechat_nickname=third_party_info.nickname,
        )

    elif platform == "alipay":
        if await self._user_dao.is_alipay_user_id_exist(third_party_info.open_id):
            raise ValueError("该支付宝账号已被其他账号绑定")

        # 更新用户信息
        await self._user_dao.update(
            user.id,
            alipay_user_id=third_party_info.open_id,
            alipay_avatar=third_party_info.avatar,
            alipay_nickname=third_party_info.nickname,
        )
    else:
        raise ValueError(f"Unsupported third-party platform: {platform}")

def new_user_service() -> UserService:
    """
    依赖注入工厂函数，创建 UserService 实例。

    注意：每次调用都会创建新实例，由 FastAPI 管理生命周期（默认每个请求一个实例）。
    DAO 使用全局单例 user_dao。
    """
    return UserService(user_dao)


# 将新方法绑定到 UserService 类
UserService.get_or_create_user_by_third_party = get_or_create_user_by_third_party
UserService.bind_third_party_account = bind_third_party_account
