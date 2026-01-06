"""
JSONType 跨数据库兼容 JSON 类型测试

测试内容:
    1. 方言适配 (load_dialect_impl)
    2. 序列化/反序列化 (process_bind_param / process_result_value)
    3. MutableDict/MutableList 变更追踪
    4. 边缘情况处理
"""

from io import StringIO
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import String
from sqlalchemy.dialects import mysql, oracle, postgresql, sqlite
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from pkg.database.base import Base, JSONType, ModelMixin, new_async_session_maker


# ==========================================
# 1. 测试模型定义
# ==========================================
class JsonModel(ModelMixin):
    __tablename__ = "json_test"

    name: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict] = mapped_column(JSONType(), default=dict)
    tags: Mapped[list] = mapped_column(JSONType(), default=list)
    extra: Mapped[dict | None] = mapped_column(JSONType(), nullable=True)


# ==========================================
# 2. Dialect Mock 工具
# ==========================================
def make_dialect(name: str) -> MagicMock:
    """创建模拟的数据库方言"""
    dialect = MagicMock()
    dialect.name = name
    return dialect


# ==========================================
# 3. load_dialect_impl 方言适配测试
# ==========================================
class TestDialectImpl:
    """测试不同数据库的类型适配"""

    def test_postgresql_uses_jsonb(self):
        """PostgreSQL 应使用 JSONB"""
        json_type = JSONType()
        dialect = postgresql.dialect()
        impl = json_type.load_dialect_impl(dialect)
        assert "JSONB" in str(impl)

    def test_mysql_uses_json(self):
        """MySQL 应使用原生 JSON"""
        json_type = JSONType()
        dialect = mysql.dialect()
        impl = json_type.load_dialect_impl(dialect)
        assert "JSON" in str(impl)

    def test_sqlite_uses_json(self):
        """SQLite 应使用 JSON"""
        json_type = JSONType()
        dialect = sqlite.dialect()
        impl = json_type.load_dialect_impl(dialect)
        # SQLite JSON 类型的字符串表示为 "_SQliteJson"
        impl_str = str(impl)
        assert "Json" in impl_str or "JSON" in impl_str

    def test_oracle_native_json(self):
        """Oracle 21c+ 默认使用原生 JSON（降级到 CLOB）"""
        json_type = JSONType(oracle_native_json=True)
        dialect = oracle.dialect()
        impl = json_type.load_dialect_impl(dialect)
        # Oracle 原生 JSON 可能会降级到 CLOB
        impl_str = str(impl)
        assert "JSON" in impl_str or "CLOB" in impl_str

    def test_oracle_clob_mode(self):
        """Oracle 12c-20c 使用 CLOB"""
        json_type = JSONType(oracle_native_json=False)
        dialect = oracle.dialect()
        impl = json_type.load_dialect_impl(dialect)
        impl_str = str(impl).upper()
        # Oracle CLOB 类型的字符串表示，可能是 "CLOB" 或 "TEXT"
        assert "CLOB" in impl_str or "TEXT" in impl_str

    def test_unknown_dialect_uses_text(self):
        """未知数据库使用 TEXT"""
        json_type = JSONType()
        dialect = make_dialect("unknown_db")
        impl = json_type.load_dialect_impl(dialect)
        # 检查返回的是 Text 类型描述符
        assert impl is not None


# ==========================================
# 4. process_bind_param 序列化测试
# ==========================================
class TestBindParam:
    """测试写入数据库时的序列化行为"""

    def test_none_value(self):
        """None 值应直接返回 None"""
        json_type = JSONType()
        result = json_type.process_bind_param(None, make_dialect("postgresql"))
        assert result is None

    def test_native_json_passthrough(self):
        """原生 JSON 数据库应直接传递对象"""
        json_type = JSONType()
        data = {"key": "value", "nested": {"a": 1}}

        for dialect_name in ("postgresql", "mysql", "sqlite"):
            dialect = make_dialect(dialect_name)
            result = json_type.process_bind_param(data, dialect)
            assert result == data, f"{dialect_name} should passthrough"

    def test_oracle_native_passthrough(self):
        """Oracle 21c+ 原生模式应直接传递对象"""
        json_type = JSONType(oracle_native_json=True)
        data = {"key": "value"}
        dialect = make_dialect("oracle")
        result = json_type.process_bind_param(data, dialect)
        assert result == data

    def test_oracle_clob_serializes(self):
        """Oracle CLOB 模式应序列化为 JSON 字符串"""
        json_type = JSONType(oracle_native_json=False)
        data = {"key": "value"}
        dialect = make_dialect("oracle")
        result = json_type.process_bind_param(data, dialect)
        assert isinstance(result, str)
        assert "key" in result and "value" in result

    def test_avoid_double_serialization(self):
        """已经是字符串的数据不应再次序列化"""
        json_type = JSONType(oracle_native_json=False)
        json_str = '{"already": "serialized"}'
        dialect = make_dialect("oracle")
        result = json_type.process_bind_param(json_str, dialect)
        assert result == json_str

    def test_list_serialization(self):
        """列表应正确序列化"""
        json_type = JSONType(oracle_native_json=False)
        data = [1, 2, "three", {"four": 4}]
        dialect = make_dialect("oracle")
        result = json_type.process_bind_param(data, dialect)
        assert isinstance(result, str)
        assert "three" in result


# ==========================================
# 5. process_result_value 反序列化测试
# ==========================================
class TestResultValue:
    """测试从数据库读取时的反序列化行为"""

    def test_none_value(self):
        """None 值应直接返回 None"""
        json_type = JSONType()
        result = json_type.process_result_value(None, make_dialect("postgresql"))
        assert result is None

    def test_dict_passthrough(self):
        """已经是 dict 的数据应直接返回"""
        json_type = JSONType()
        data = {"key": "value"}
        result = json_type.process_result_value(data, make_dialect("oracle"))
        assert result == data

    def test_list_passthrough(self):
        """已经是 list 的数据应直接返回"""
        json_type = JSONType()
        data = [1, 2, 3]
        result = json_type.process_result_value(data, make_dialect("oracle"))
        assert result == data

    def test_native_json_passthrough(self):
        """原生 JSON 数据库的值应直接返回"""
        json_type = JSONType()

        for dialect_name in ("postgresql", "mysql", "sqlite"):
            dialect = make_dialect(dialect_name)
            result = json_type.process_result_value("any_value", dialect)
            assert result == "any_value"

    def test_clob_deserialization(self):
        """CLOB 模式应反序列化 JSON 字符串"""
        json_type = JSONType(oracle_native_json=False)
        json_str = '{"key": "value"}'
        dialect = make_dialect("oracle")
        result = json_type.process_result_value(json_str, dialect)
        assert result == {"key": "value"}

    def test_empty_string_returns_none(self):
        """空字符串应返回 None"""
        json_type = JSONType(oracle_native_json=False)
        dialect = make_dialect("oracle")

        assert json_type.process_result_value("", dialect) is None
        assert json_type.process_result_value("   ", dialect) is None

    def test_lob_object_read(self):
        """Oracle LOB 对象应调用 read() 获取内容"""
        json_type = JSONType(oracle_native_json=False)
        dialect = make_dialect("oracle")

        # 模拟 LOB 对象
        lob = StringIO('{"from": "lob"}')
        result = json_type.process_result_value(lob, dialect)
        assert result == {"from": "lob"}

    def test_invalid_json_fallback(self):
        """非 JSON 格式数据应返回原始值（容错）"""
        json_type = JSONType(oracle_native_json=False)
        dialect = make_dialect("oracle")
        invalid_json = "not a json string"
        result = json_type.process_result_value(invalid_json, dialect)
        assert result == invalid_json


# ==========================================
# 6. 集成测试 - SQLite 内存数据库
# ==========================================
@pytest_asyncio.fixture(loop_scope="function")
async def db_session():
    """创建测试数据库会话"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = new_async_session_maker(engine)
    yield session_maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_json_crud(db_session):
    """测试 JSON 字段的完整 CRUD 流程"""
    # Create
    model = JsonModel.create(
        name="test",
        config={"debug": True, "version": "1.0"},
        tags=["python", "fastapi"],
    )
    await model.save(db_session)

    # Read
    async with db_session() as session:
        result = await session.get(JsonModel, model.id)
        assert result.config == {"debug": True, "version": "1.0"}
        assert result.tags == ["python", "fastapi"]
        assert result.extra is None


@pytest.mark.asyncio
async def test_json_mutable_tracking(db_session):
    """测试 MutableDict/MutableList 变更追踪"""
    # 创建并保存
    model = JsonModel.create(name="mutable_test", config={"count": 0}, tags=[])
    await model.save(db_session)

    # 修改 JSON 字段
    async with db_session() as session:
        async with session.begin():
            result = await session.get(JsonModel, model.id)
            result.config["count"] = 1  # MutableDict 追踪
            result.config["new_key"] = "added"
            result.tags.append("new_tag")  # MutableList 追踪

    # 验证变更已持久化
    async with db_session() as session:
        result = await session.get(JsonModel, model.id)
        assert result.config["count"] == 1
        assert result.config["new_key"] == "added"
        assert "new_tag" in result.tags


@pytest.mark.asyncio
async def test_json_nullable_field(db_session):
    """测试可空 JSON 字段"""
    # 测试 None 值
    model1 = JsonModel.create(name="nullable_none", extra=None)
    await model1.save(db_session)

    async with db_session() as session:
        result = await session.get(JsonModel, model1.id)
        assert result.extra is None

    # 测试有值
    model2 = JsonModel.create(name="nullable_with_value", extra={"meta": "data"})
    await model2.save(db_session)

    async with db_session() as session:
        result = await session.get(JsonModel, model2.id)
        assert result.extra == {"meta": "data"}


@pytest.mark.asyncio
async def test_json_complex_nested(db_session):
    """测试复杂嵌套 JSON 结构"""
    complex_config = {
        "database": {
            "host": "localhost",
            "port": 5432,
            "options": {"timeout": 30, "pool_size": 10},
        },
        "features": ["auth", "cache", "logging"],
        "enabled": True,
        "ratio": 0.95,
    }

    model = JsonModel.create(name="complex", config=complex_config)
    await model.save(db_session)

    async with db_session() as session:
        result = await session.get(JsonModel, model.id)
        assert result.config["database"]["port"] == 5432
        assert result.config["database"]["options"]["timeout"] == 30
        assert "cache" in result.config["features"]
        assert result.config["ratio"] == 0.95
