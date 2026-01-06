import os
import sys
import types
from datetime import datetime
from unittest.mock import MagicMock
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import String
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

# ==========================================
# 1. Mock 策略 (保持不变)
# ==========================================

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
pkg_path = os.path.join(project_root, "pkg")

# 1.1 Mock pkg.toolkit.json
mock_json = types.ModuleType("pkg.toolkit.json")
mock_json.orjson_dumps = lambda x, **kwargs: '{"mock": "json"}'
mock_json.orjson_loads = lambda x: {"mock": "json"}
mock_json.JsonInputType = str | bytes
sys.modules["pkg.toolkit.json"] = mock_json

# 1.2 Mock pkg.toolkit.timer
mock_timer = types.ModuleType("pkg.toolkit.timer")
mock_timer.utc_now_naive = lambda: datetime.utcnow()
sys.modules["pkg.toolkit.timer"] = mock_timer

# 1.3 Mock pkg.toolkit.context
mock_ctx_module = types.ModuleType("pkg.toolkit.context")
mock_ctx_func = MagicMock()
mock_ctx_func.return_value = 999
mock_ctx_module.get_user_id = mock_ctx_func
sys.modules["pkg.toolkit.context"] = mock_ctx_module
sys.modules["pkg.context"] = mock_ctx_module

# 1.4 Mock 其他工具
mock_logger = MagicMock()
mock_snowflake = MagicMock()
_id_counter = 0


def mock_gen_id():
    global _id_counter
    _id_counter += 1
    return _id_counter


mock_snowflake.generate_snowflake_id = mock_gen_id
sys.modules["pkg.logger_tool"] = mock_logger
sys.modules["pkg.toolkit.inter.snowflake_id_generator"] = mock_snowflake

# ==========================================
# 2. 导入目标代码
# ==========================================
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from pkg.database.base import Base, ModelMixin, JSONType, new_async_session_maker
    from pkg.database.dao import BaseDao
except ImportError as e:
    try:
        from pkg.database import ModelMixin, BaseDao, Base, new_async_session_maker, JSONType
    except ImportError:
        print(f"CRITICAL: Cannot import from pkg.database. path={sys.path}")
        raise e


# ==========================================
# 3. 定义测试模型
# ==========================================
class User(ModelMixin):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(100), nullable=True)
    info: Mapped[dict] = mapped_column(JSONType, default=dict)


class UserDao(BaseDao[User]):
    pass


# ==========================================
# 4. Pytest Fixtures
# ==========================================


@pytest_asyncio.fixture(loop_scope="function")
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = new_async_session_maker(engine)
    yield session_maker
    await engine.dispose()


@pytest.fixture
def user_dao(db_session):
    return UserDao(session_provider=db_session, model_cls=User)


# ==========================================
# 5. 测试用例
# ==========================================


@pytest.mark.asyncio
async def test_create_and_save_strictness(user_dao, db_session):
    """测试创建对象、严格Save检查和ID生成"""
    user = User.create(username="alice", info={"role": "admin"})
    assert user.id is not None
    assert user.info == {"role": "admin"}

    await user.save(db_session)

    db_user = await user_dao.query_by_primary_id(user.id)
    assert db_user is not None
    assert db_user.username == "alice"
    assert db_user.info == {"role": "admin"}

    with pytest.raises(RuntimeError) as exc:
        await db_user.save(db_session)
    assert "strictly for INSERT" in str(exc.value)


@pytest.mark.asyncio
async def test_update_strictness(user_dao, db_session):
    """测试更新逻辑、Mutable JSON 追踪和严格Update检查"""
    # 初始化
    user = User.create(username="bob", info={"login_count": 0})
    await user.save(db_session)

    # 1. Update Persistent Object
    async with db_session() as session:
        # [修复点] 移除 async with session.begin():
        # 因为 update() 方法内部会自己开启事务，重复开启会导致冲突。
        # session.get 不需要显式事务（Autobegin）

        db_user = await session.get(User, user.id)

        # 修改 JSON 内部字段 (验证 MutableJSON)
        db_user.info["login_count"] = 1
        db_user.info["last_login"] = "today"

        # 定义一个不关闭 Session 的 Provider，防止 update 后 session 被关闭
        # 虽然在这个测试块末尾 session 本来就要关闭，但这是好习惯
        @asynccontextmanager
        async def reuse_session():
            yield session

        # 执行更新 (内部会 commit)
        await db_user.update(reuse_session, username="bob_updated")

    # 2. 验证变更
    # 使用新的 Session 查询，确保数据已落库
    reloaded = await user_dao.query_by_primary_id(user.id)

    assert reloaded.username == "bob_updated"
    assert reloaded.updater_id == 999
    # 验证 JSON 变更被持久化了
    assert reloaded.info["login_count"] == 1, "JSON Mutation failed to track changes"
    assert "last_login" in reloaded.info

    # 3. Strict Update 检查
    new_user = User.create(username="charlie")
    with pytest.raises(RuntimeError) as exc:
        await new_user.update(db_session, username="fail")
    assert "strictly for UPDATE" in str(exc.value)


@pytest.mark.asyncio
async def test_batch_insert_instances(user_dao, db_session):
    users = [User.create(username=f"user_{i}") for i in range(5)]
    await User.insert_instances(items=users, session_provider=db_session)
    count = await user_dao.counter.count()
    assert count == 5


@pytest.mark.asyncio
async def test_batch_insert_rows(user_dao, db_session):
    rows = [{"username": "dict_1"}, {"username": "dict_2"}]
    await User.insert_rows(rows=rows, session_provider=db_session)
    count = await user_dao.counter.count()
    assert count == 2


@pytest.mark.asyncio
async def test_query_builder(user_dao, db_session):
    await User.insert_rows(rows=[{"username": f"u{i}"} for i in range(1, 6)], session_provider=db_session)

    res = await user_dao.querier.in_(User.username, ["u1", "u2"]).all()
    assert len(res) == 2

    with pytest.raises(ValueError) as exc:
        await user_dao.querier.in_(User.username, []).all()
    assert "empty" in str(exc.value) or "Empty" in str(exc.value)

    page_res = await user_dao.querier_unsorted.asc_(User.id).paginate(page=1, limit=2).all()
    assert len(page_res) == 2
    assert page_res[0].username == "u1"


@pytest.mark.asyncio
async def test_soft_delete(user_dao, db_session):
    user = User.create(username="del_me")
    await user.save(db_session)
    await user_dao.ins_updater(user).soft_delete()
    assert await user_dao.querier.eq_(User.id, user.id).first() is None
    assert await user_dao.querier_inc_deleted.eq_(User.id, user.id).first() is not None


@pytest.mark.asyncio
async def test_updater_builder_logic(user_dao, db_session):
    user = User.create(username="old_name")
    await user.save(db_session)
    await user_dao.ins_updater(user).update(username="new_name")
    reloaded = await user_dao.query_by_primary_id(user.id)
    assert reloaded.username == "new_name"


if __name__ == "__main__":
    sys.exit(pytest.main(["-s", "-v", __file__]))
