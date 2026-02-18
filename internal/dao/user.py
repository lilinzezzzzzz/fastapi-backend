from internal.infra.database import get_read_session, get_session
from internal.models.user import User
from pkg.database.dao import BaseDao


class UserDao(BaseDao[User]):
    _model_cls: type[User] = User

    async def get_by_phone(self, phone: str) -> User | None:
        # 建议方法名更加简洁，因为已经在 UserDao 里了，不用写 get_user_by_phone
        # 使用你构建的 querier
        return await self.querier.eq_(User.phone, phone).first()

    async def get_by_username(self, username: str) -> User | None:
        """根据用户名查询用户"""
        return await self.querier.eq_(User.name, username).first()

    async def is_phone_exist(self, phone: str) -> bool:
        # 利用你封装的 count
        count = await self.counter.eq_(User.phone, phone).count()
        return count > 0

    async def get_by_wechat_openid(self, openid: str) -> User | None:
        """通过微信 openid 查询用户"""
        return await self.querier.eq_(User.wechat_openid, openid).first()

    async def is_wechat_openid_exist(self, openid: str) -> bool:
        """检查微信 openid 是否已存在"""
        count = await self.counter.eq_(User.wechat_openid, openid).count()
        return count > 0

    async def get_by_alipay_user_id(self, user_id: str) -> User | None:
        """通过支付宝用户 ID 查询用户"""
        return await self.querier.eq_(User.alipay_user_id, user_id).first()

    async def is_alipay_user_id_exist(self, user_id: str) -> bool:
        """检查支付宝用户 ID 是否已存在"""
        count = await self.counter.eq_(User.alipay_user_id, user_id).count()
        return count > 0


# 单例模式 (Singleton)
# 在简单的应用中，直接实例化一个全局 dao 是没问题的
# 因为 session_provider 是一个工厂函数，不会在 import 时建立连接
user_dao = UserDao(
    session_provider=get_session,
    read_session_provider=get_read_session,
)
