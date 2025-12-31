"""
测试 pkg/toolkit/json.py 和 pkg/toolkit/response.py 的功能完整性和正确性
"""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import BaseModel

# numpy 可能不在测试环境中
try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore
    HAS_NUMPY = False

from pkg.toolkit.json import orjson_dumps, orjson_dumps_bytes, orjson_loads
from pkg.toolkit.response import (
    AppError,
    AppStatus,
    CustomORJSONResponse,
    error_response,
    success_list_response,
    success_response,
    wrap_sse_data,
)

# =========================================================
# 1. orjson 序列化测试
# =========================================================


class TestOrjsonDumps:
    """测试 orjson_dumps 和 orjson_dumps_bytes 函数"""

    def test_basic_types(self):
        """测试基本类型序列化"""
        data = {
            "large_int": 2**53 + 1,  # 超过JS安全整数
            "normal_int": 42,
            "float_num": 3.1415926535,
            "boolean": True,
            "none_value": None,
        }
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        assert parsed["large_int"] == 2**53 + 1
        assert parsed["normal_int"] == 42
        assert parsed["float_num"] == 3.1415926535
        assert parsed["boolean"] is True
        assert parsed["none_value"] is None

    def test_containers(self):
        """测试容器类型序列化"""
        data = {
            "set_data": {1, 2, 3},  # 集合转列表
            "list_data": [1, 2, 3],
        }
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        # 集合会被转换为列表
        assert set(parsed["set_data"]) == {1, 2, 3}
        assert parsed["list_data"] == [1, 2, 3]

    def test_datetime_serialization(self):
        """测试日期时间序列化"""
        naive_dt = datetime(2023, 1, 1, 12, 0, 0)
        aware_dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)

        data = {
            "naive": naive_dt,
            "aware": aware_dt,
        }
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        # 验证日期格式正确
        assert "2023-01-01" in parsed["naive"]
        assert "2023-01-01" in parsed["aware"]

    def test_decimal_safe_range(self):
        """测试 Decimal 在安全范围内转为 float"""
        data = {
            "normal": Decimal("999.999"),
            "zero": Decimal("0.000000"),
        }
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        # 安全范围内的 Decimal 转为 float
        assert parsed["normal"] == 999.999
        assert parsed["zero"] == 0.0

    def test_decimal_high_precision(self):
        """测试高精度 Decimal 转为字符串"""
        data = {
            "high_precision": Decimal("0.12345678901234567890123456789"),  # 超过6位小数
            "large_decimal": Decimal("1e16"),  # 超过 1e15 范围
        }
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        # 高精度或超范围 Decimal 转为字符串
        assert isinstance(parsed["high_precision"], str)
        assert isinstance(parsed["large_decimal"], str)

    def test_bytes_serialization(self):
        """测试字节序列化"""
        data = {"bytes": b"hello"}
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        assert parsed["bytes"] == "hello"

    def test_bytes_with_invalid_utf8(self):
        """测试包含无效 UTF-8 的字节"""
        data = {"bytes": b"\x80abc\xff"}
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        # 无效字节被忽略
        assert parsed["bytes"] == "abc"

    def test_timedelta_serialization(self):
        """测试时间间隔序列化"""
        data = {"timedelta": timedelta(days=1, seconds=3600)}
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        # timedelta 转换为总秒数
        assert parsed["timedelta"] == 86400 + 3600

    def test_uuid_serialization(self):
        """测试 UUID 序列化"""
        test_uuid = uuid.uuid4()
        data = {"uuid": test_uuid}
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        assert parsed["uuid"] == str(test_uuid)

    @pytest.mark.skipif(not HAS_NUMPY, reason="numpy not installed")
    def test_numpy_array(self):
        """测试 NumPy 数组序列化"""
        data = {"array": np.array([1.1, 2.2, 3.3])}
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        assert parsed["array"] == [1.1, 2.2, 3.3]

    @pytest.mark.skipif(not HAS_NUMPY, reason="numpy not installed")
    def test_numpy_int64(self):
        """测试 NumPy int64 序列化"""
        data = {"int64": np.int64(2**63 - 1)}
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        assert parsed["int64"] == 2**63 - 1

    def test_nested_structure(self):
        """测试嵌套结构序列化"""
        test_uuid = uuid.uuid4()
        data = {
            "level1": {
                "level2": [
                    {
                        "mixed_types": [
                            Decimal("999.999"),
                            {str(test_uuid): datetime.now().isoformat()},
                            [2**60, {"deep": True}],
                        ]
                    }
                ]
            }
        }
        result = orjson_dumps(data)
        parsed = orjson_loads(result)

        assert "level1" in parsed
        assert "level2" in parsed["level1"]
        assert parsed["level1"]["level2"][0]["mixed_types"][0] == 999.999

    def test_dumps_bytes_returns_bytes(self):
        """测试 orjson_dumps_bytes 返回 bytes"""
        data = {"key": "value"}
        result = orjson_dumps_bytes(data)

        assert isinstance(result, bytes)
        assert result == b'{"key":"value"}'

    def test_dumps_returns_str(self):
        """测试 orjson_dumps 返回 str"""
        data = {"key": "value"}
        result = orjson_dumps(data)

        assert isinstance(result, str)
        assert result == '{"key":"value"}'

    def test_unsupported_type_raises_error(self):
        """测试不支持的类型抛出异常"""

        class CustomClass:
            pass

        data = {"custom": CustomClass()}

        with pytest.raises(ValueError, match="JSON Serialization Failed"):
            orjson_dumps(data)


class TestOrjsonLoads:
    """测试 orjson_loads 函数"""

    def test_loads_from_str(self):
        """测试从字符串反序列化"""
        result = orjson_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_loads_from_bytes(self):
        """测试从字节反序列化"""
        result = orjson_loads(b'{"key": "value"}')
        assert result == {"key": "value"}

    def test_loads_invalid_json(self):
        """测试无效 JSON 抛出异常"""
        with pytest.raises(ValueError, match="JSON Deserialization Failed"):
            orjson_loads("invalid json")


# =========================================================
# 2. 响应工厂测试
# =========================================================


class UserSchema(BaseModel):
    """测试用 Pydantic 模型"""

    id: int
    name: str


class TestSuccessResponse:
    """测试 success_response 函数"""

    def test_success_with_dict(self):
        """测试字典数据响应"""
        response = success_response(data={"key": "value"})

        assert isinstance(response, CustomORJSONResponse)
        assert response.status_code == 200

    def test_success_with_none(self):
        """测试 None 数据响应"""
        response = success_response(data=None)

        assert isinstance(response, CustomORJSONResponse)
        assert response.status_code == 200

    def test_success_with_list(self):
        """测试列表数据响应"""
        response = success_response(data=[1, 2, 3])

        assert isinstance(response, CustomORJSONResponse)

    def test_success_with_pydantic_model(self):
        """测试 Pydantic 模型响应"""
        user = UserSchema(id=1, name="test")
        response = success_response(data=user)

        assert isinstance(response, CustomORJSONResponse)

    def test_success_with_pydantic_list(self):
        """测试 Pydantic 模型列表响应"""
        users = [UserSchema(id=1, name="user1"), UserSchema(id=2, name="user2")]
        response = success_response(data=users)

        assert isinstance(response, CustomORJSONResponse)

    def test_success_with_invalid_type(self):
        """测试无效类型抛出异常"""
        with pytest.raises(TypeError, match="Success response data must be"):
            success_response(data="invalid")  # type: ignore


class TestSuccessListResponse:
    """测试 success_list_response 函数"""

    def test_list_response(self):
        """测试分页列表响应"""
        response = success_list_response(data=[1, 2, 3], page=1, limit=10, total=100)

        assert isinstance(response, CustomORJSONResponse)

    def test_list_response_with_pydantic(self):
        """测试 Pydantic 模型列表分页响应"""
        users = [UserSchema(id=1, name="user1")]
        response = success_list_response(data=users, page=1, limit=10, total=1)

        assert isinstance(response, CustomORJSONResponse)

    def test_list_response_invalid_items(self):
        """测试无效 items 类型抛出异常"""
        with pytest.raises(TypeError, match="Items must be a list"):
            success_list_response(data="invalid", page=1, limit=10, total=1)  # type: ignore


class TestErrorResponse:
    """测试 error_response 函数"""

    def test_error_response_basic(self):
        """测试基本错误响应"""
        error = AppError(40000, {"zh": "请求参数错误", "en": "Bad Request"})
        response = error_response(error)

        assert isinstance(response, CustomORJSONResponse)
        assert response.status_code == 200

    def test_error_response_with_message(self):
        """测试带自定义消息的错误响应"""
        error = AppError(40000, {"zh": "请求参数错误", "en": "Bad Request"})
        response = error_response(error, message="字段缺失")

        assert isinstance(response, CustomORJSONResponse)

    def test_error_response_with_lang(self):
        """测试英文错误响应"""
        error = AppError(40000, {"zh": "请求参数错误", "en": "Bad Request"})
        response = error_response(error, lang="en")

        assert isinstance(response, CustomORJSONResponse)


# =========================================================
# 3. AppStatus 和 AppError 测试
# =========================================================


class TestAppStatus:
    """测试 AppStatus 类"""

    def test_get_msg_default_zh(self):
        """测试默认获取中文消息"""
        status = AppStatus(20000, {"zh": "成功", "en": "Success"})
        assert status.get_msg() == "成功"

    def test_get_msg_en(self):
        """测试获取英文消息"""
        status = AppStatus(20000, {"zh": "成功", "en": "Success"})
        assert status.get_msg("en") == "Success"

    def test_get_msg_fallback(self):
        """测试语言回退到中文"""
        status = AppStatus(20000, {"zh": "成功"})
        assert status.get_msg("fr") == "成功"

    def test_repr(self):
        """测试字符串表示"""
        status = AppStatus(20000, {"zh": "成功"})
        assert "20000" in repr(status)


class TestAppError:
    """测试 AppError 类"""

    def test_app_error_is_app_status(self):
        """测试 AppError 继承自 AppStatus"""
        error = AppError(40000, {"zh": "错误", "en": "Error"})
        assert isinstance(error, AppStatus)

    def test_app_error_frozen(self):
        """测试 AppError 是不可变的"""
        error = AppError(40000, {"zh": "错误"})
        with pytest.raises(Exception):  # frozen dataclass 不可修改
            error.code = 50000  # type: ignore


# =========================================================
# 4. SSE 包装测试
# =========================================================


class TestWrapSseData:
    """测试 wrap_sse_data 函数"""

    def test_wrap_string(self):
        """测试字符串包装"""
        result = wrap_sse_data("hello")
        assert result == "data: hello\n\n"

    def test_wrap_dict(self):
        """测试字典包装"""
        result = wrap_sse_data({"key": "value"})
        assert result == 'data: {"key":"value"}\n\n'

    def test_wrap_dict_with_chinese(self):
        """测试包含中文的字典"""
        result = wrap_sse_data({"msg": "你好"})
        assert "你好" in result
        assert result.startswith("data: ")
        assert result.endswith("\n\n")


# =========================================================
# 5. CustomORJSONResponse 测试
# =========================================================


class TestCustomORJSONResponse:
    """测试 CustomORJSONResponse 类"""

    def test_render_returns_bytes(self):
        """测试 render 返回 bytes"""
        response = CustomORJSONResponse(content={"key": "value"})
        body = response.body

        assert isinstance(body, bytes)

    def test_media_type(self):
        """测试媒体类型"""
        response = CustomORJSONResponse(content={})
        assert response.media_type == "application/json"

    def test_render_complex_data(self):
        """测试复杂数据渲染"""
        data = {
            "decimal": Decimal("123.45"),
            "datetime": datetime.now(),
            "uuid": uuid.uuid4(),
        }
        response = CustomORJSONResponse(content=data)
        body = response.body

        assert isinstance(body, bytes)
        # 验证可以正常解析
        parsed = orjson_loads(body)
        assert "decimal" in parsed
        assert "datetime" in parsed
        assert "uuid" in parsed


if __name__ == "__main__":
    # 允许直接运行此文件调试
    sys.exit(pytest.main(["-s", "-v", "--log-cli-level=INFO", __file__]))
