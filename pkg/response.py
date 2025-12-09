import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import orjson
from fastapi.responses import ORJSONResponse


# =========================================================
# 1. 定义错误结构与全局状态码
# =========================================================


@dataclass(frozen=True)
class AppError:
    """
    应用错误对象 (Rich Error Object)
    将错误码与多语言文案绑定在一起
    """

    code: int
    message: dict[str, str]

    def get_msg(self, lang: str = "zh") -> str:
        """根据语言获取文案，默认回退到中文"""
        return self.message.get(lang, self.message.get("zh", "Unknown Error"))


class GlobalCodes:
    """
    全局状态码定义
    不使用 Enum，直接使用类属性，方便代码跳转和类型提示
    """

    Success = AppError(20000, {"zh": "操作成功", "en": "Success"})

    # 客户端错误 (40000 - 49999)
    BadRequest = AppError(40000, {"zh": "请求参数错误", "en": "Bad Request"})
    Unauthorized = AppError(40001, {"zh": "未授权，请登录", "en": "Unauthorized"})
    Forbidden = AppError(40003, {"zh": "权限不足，禁止访问", "en": "Forbidden"})
    NotFound = AppError(40004, {"zh": "资源不存在", "en": "Not Found"})
    PayloadTooLarge = AppError(40005, {"zh": "请求载荷过大", "en": "Payload Too Large"})
    UnprocessableEntity = AppError(40006, {"zh": "无法处理的实体", "en": "Unprocessable Entity"})

    # 服务端错误 (50000 - 59999)
    InternalServerError = AppError(50000, {"zh": "服务器内部错误", "en": "Internal Server Error"})


global_codes = GlobalCodes


# =========================================================
# 2. 高性能 JSON 响应类
# =========================================================


class CustomORJSONResponse(ORJSONResponse):
    """
    基于 orjson 的高性能响应类。
    优化点：移除手动递归，仅在 default 回调中处理特殊类型。
    """

    SERIALIZER_OPTIONS = (
        orjson.OPT_SERIALIZE_NUMPY
        | orjson.OPT_SERIALIZE_UUID
        | orjson.OPT_NAIVE_UTC
        | orjson.OPT_UTC_Z
        | orjson.OPT_OMIT_MICROSECONDS
        | orjson.OPT_NON_STR_KEYS
    )

    def render(self, content: Any) -> bytes:
        def default_serializer(obj: Any) -> Any:
            """
            仅处理 orjson 原生不支持的类型
            """
            if isinstance(obj, Decimal):
                # 如果是小数且在浮点数安全范围内(-1e15 ~ 1e15)，转 float；否则转 str 避免精度丢失
                return float(obj) if -1e15 < obj < 1e15 and obj.as_tuple().exponent >= -6 else str(obj)

            if isinstance(obj, bytes):
                return obj.decode("utf-8", "ignore")

            if isinstance(obj, datetime.timedelta):
                return obj.total_seconds()

            if isinstance(obj, (set, frozenset)):
                return list(obj)

            # 注意：orjson 原生支持 int，大整数处理建议在 Pydantic model 层解决
            raise TypeError(f"Type {type(obj)} not serializable")

        try:
            return orjson.dumps(
                content,
                option=self.SERIALIZER_OPTIONS,
                default=default_serializer,
            )
        except Exception as e:
            raise ValueError(f"JSON serialization failed: {e}") from e


# =========================================================
# 3. 响应工厂
# =========================================================


class ResponseFactory:
    @staticmethod
    def _make_response(
        *, code: int, data: Any = None, message: str = "", http_status: int = 200
    ) -> CustomORJSONResponse:
        """基础响应构造器"""
        return CustomORJSONResponse(
            status_code=http_status,
            content={
                "code": code,
                "message": message,
                "data": data,
            },
        )

    def success(self, *, data: Any = None, message: str = "", lang: str = "zh") -> CustomORJSONResponse:
        """
        成功响应
        """
        if not message:
            message = GlobalCodes.Success.get_msg(lang)
        return self._make_response(code=GlobalCodes.Success.code, data=data, message=message)

    def list(self, *, data: list, page: int, limit: int, total: int) -> CustomORJSONResponse:
        """
        分页列表响应
        """
        return self.success(data={"items": data, "meta": {"page": page, "limit": limit, "total": total}})

    def error(self, error: AppError, *, message: str = "", data: Any = None, lang: str = "zh") -> CustomORJSONResponse:
        """
        通用错误响应。

        Args:
            error: GlobalCodes 中定义的错误对象
            message: 自定义详细信息。如果传入，将拼接到默认文案后面。
            data: 附加数据
            lang: 语言代码 ('zh', 'en')，默认为 'zh'

        Examples:
            >>> response_factory.error(GlobalCodes.BadRequest, message="ID不能为空")
            >>> # Result: message="请求参数错误: ID不能为空"
        """
        # 1. 获取预定义的错误信息 (例如 "请求参数错误")
        base_msg = error.get_msg(lang)

        # 2. 拼接逻辑
        if message:
            final_message = f"{base_msg}: {message}"
        else:
            final_message = base_msg

        return self._make_response(code=error.code, message=final_message, data=data)


# 全局单例
response_factory = ResponseFactory()


# =========================================================
# 4. 工具函数
# =========================================================


def wrap_sse_data(content: str | dict) -> str:
    """
    将内容包装为 SSE (Server-Sent Events) 格式
    """
    if isinstance(content, dict):
        # 序列化并确保是 utf-8 字符串
        content = orjson.dumps(content).decode("utf-8")
    return f"data: {content}\n\n"
