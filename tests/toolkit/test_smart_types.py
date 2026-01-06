import json
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

# 引入我们定义的类型
from pkg.toolkit.types import JS_MAX_SAFE_INTEGER, SmartDatetime, SmartDecimal, SmartInt


# 定义一个用于测试的模型
class DemoModel(BaseModel):
    id: SmartInt | None = None
    score: SmartDecimal | None = None
    created_at: SmartDatetime | None = None


# ==========================================
# 1. 测试 SmartInt
# ==========================================
class TestSmartInt:

    def test_smart_int_safe_range(self):
        """测试 JS 安全范围内的整数 -> JSON 保持数字"""
        input_val = 12345
        model = DemoModel(id=input_val)

        # 验证内部类型
        assert isinstance(model.id, int)
        assert model.id == 12345

        # 验证 JSON 输出 (保持 int)
        json_data = json.loads(model.model_dump_json())
        assert json_data['id'] == 12345
        assert isinstance(json_data['id'], int)

    def test_smart_int_unsafe_range(self):
        """测试超过 JS 安全范围的整数 -> JSON 转为字符串"""
        # 构造一个比 JS 最大安全整数大 1 的数
        unsafe_val = JS_MAX_SAFE_INTEGER + 1
        model = DemoModel(id=unsafe_val)

        # 验证内部类型 (依然是 int，方便 Python 计算)
        assert isinstance(model.id, int)
        assert model.id == unsafe_val

        # 验证 JSON 输出 (转为 str)
        json_data = json.loads(model.model_dump_json())
        assert json_data['id'] == str(unsafe_val)
        assert isinstance(json_data['id'], str)

    def test_smart_int_from_string(self):
        """测试前端传字符串数字 -> 内部转 int"""
        model = DemoModel(id="999")
        assert model.id == 999
        assert isinstance(model.id, int)

    def test_smart_int_invalid(self):
        """测试非法输入"""
        with pytest.raises(ValidationError):
            DemoModel(id="not-a-number")


# ==========================================
# 2. 测试 SmartDecimal
# ==========================================
class TestSmartDecimal:

    def test_smart_decimal_simple(self):
        """测试简单浮点数 (精度低) -> JSON 转 float"""
        # 输入字符串以避免 float 初始化的精度干扰，模拟前端 JSON 传参
        model = DemoModel(score="10.5")

        # 验证内部类型
        assert isinstance(model.score, Decimal)
        assert model.score == Decimal("10.5")

        # 验证 JSON 输出 (转为 float)
        json_data = json.loads(model.model_dump_json())
        assert json_data['score'] == 10.5
        assert isinstance(json_data['score'], float)

    def test_smart_decimal_high_precision(self):
        """测试高精度小数 (>6位小数) -> JSON 转 str"""
        val = "0.1234567"  # 7位小数
        model = DemoModel(score=val)

        # 验证内部类型
        assert isinstance(model.score, Decimal)

        # 验证 JSON 输出 (保留精度，转为 str)
        json_data = json.loads(model.model_dump_json())
        assert json_data['score'] == val
        assert isinstance(json_data['score'], str)

    def test_smart_decimal_large_number(self):
        """测试超大数值 -> JSON 转 str"""
        val = "10000000000000001"  # 超过 1e16
        model = DemoModel(score=val)

        json_data = json.loads(model.model_dump_json())
        assert json_data['score'] == val
        assert isinstance(json_data['score'], str)


# ==========================================
# 3. 测试 SmartDatetime
# ==========================================
class TestSmartDatetime:

    def test_smart_datetime_from_iso_string(self):
        """测试 ISO 字符串输入 (带 Z)"""
        input_str = "2025-12-09T10:30:00Z"
        model = DemoModel(created_at=input_str)

        # 验证内部类型 (datetime, 无时区)
        assert isinstance(model.created_at, datetime)
        assert model.created_at.year == 2025
        assert model.created_at.tzinfo is None

        # 验证 JSON 输出
        json_data = json.loads(model.model_dump_json())
        # 输出时不带 Z，单纯的 ISO 格式
        assert json_data['created_at'] == "2025-12-09T10:30:00"

    def test_smart_datetime_from_obj(self):
        """测试直接传 datetime 对象"""
        dt = datetime(2025, 5, 20, 13, 14, 0)
        model = DemoModel(created_at=dt)

        assert model.created_at == dt

        json_data = json.loads(model.model_dump_json())
        assert json_data['created_at'] == "2025-05-20T13:14:00"

    def test_smart_datetime_invalid(self):
        """测试非法日期格式"""
        with pytest.raises(ValidationError):
            DemoModel(created_at="invalid-date-format")
