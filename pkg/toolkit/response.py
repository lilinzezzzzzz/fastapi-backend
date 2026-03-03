from dataclasses import dataclass
from typing import Any

from fastapi.responses import ORJSONResponse
from pydantic import BaseModel

from pkg.toolkit.json import orjson_dumps, orjson_dumps_bytes

# =========================================================
# 1. 定义状态码结构与全局状态码
# =========================================================


@dataclass(frozen=True)
class AppStatus:
    """
    应用状态对象基类
    将状态码与多语言文案绑定在一起
    """

    code: int
    message: dict[str, str]

    def get_message(self, lang: str = "zh") -> str:
        """根据语言获取文案，默认回退到中文"""
        return self.message.get(lang) or self.message["zh"]


success_status = AppStatus(20000, {"zh": "", "en": "success"})


@dataclass(frozen=True)
class AppError(AppStatus):
    """
    专门用于表示应用错误的子类 (继承自 AppStatus)
    """

    def __repr__(self) -> str:
        return f"(code={self.code}, message={self.message})"


# =========================================================
# 2. 高性能 JSON 响应类
# =========================================================


@dataclass
class _ResponseBody:
    """
    统一响应体结构
    """

    code: int = 20000
    message: str = ""
    data: Any = None

    def to_dict(self) -> dict:
        """转换为字典，保留 None 值"""
        return {"code": self.code, "message": self.message, "data": self.data}


class CustomORJSONResponse(ORJSONResponse):
    """
    基于 orjson 的高性能响应类。

    Architecture Note:
        序列化逻辑已下沉至 `pkg.toolkit.json`，确保 Worker 任务与 Web 接口
        使用完全一致的序列化标准（如 Decimal 和 Numpy 的处理）。
    """

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        """
        覆写 render 方法。
        直接返回 bytes，避免 Starlette 内部再次进行 .encode('utf-8')。
        """
        # 无需 try-catch，工具函数内部已处理并抛出清洗后的 ValueError，
        # 框架的 ExceptionHandler 会捕获它。
        return orjson_dumps_bytes(content)


# =========================================================
# 3. 响应工厂
# =========================================================


class _ResponseFactory:
    @staticmethod
    def _make_response(
        *, code: int, data: Any = None, message: str = "", http_status: int = 200
    ) -> CustomORJSONResponse:
        """基础响应构造器"""
        response_body = _ResponseBody(code=code, message=message, data=data)
        return CustomORJSONResponse(
            status_code=http_status,
            content=response_body.to_dict(),
        )

    @staticmethod
    def _process_success_data(data: dict | list | BaseModel | None = None) -> dict | list | None:
        """
        验证成功响应的数据类型，并将其转换为最优格式（dict）。

        Args:
            data: 传入的响应数据。

        Returns:
            转换后的 dict、list 或 None。

        Raises:
            TypeError: 如果数据类型不符合要求。
        """
        if data is None:
            return data

        # 1. 🌟 优先处理 Pydantic 模型并转换
        if isinstance(data, BaseModel):
            return data.model_dump(mode="json")

        # 2. 处理列表，检查元素是否为 BaseModel
        if isinstance(data, list):
            return [item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in data]

        # 3. 接着检查 Python 原生类型 (dict)
        if isinstance(data, dict):
            return data

        # 4. 如果都不是，抛出错误
        raise TypeError(
            f"Success response data must be a dict, list, a Pydantic model instance, or None, but received type: {type(data)}"
        )

    def success(self, *, data: dict | list | BaseModel | None = None) -> CustomORJSONResponse:
        """
        成功响应
        """
        data = self._process_success_data(data)
        return self._make_response(code=success_status.code, data=data)

    def list(self, *, items: list, page: int, limit: int, total: int) -> CustomORJSONResponse:
        """
        分页列表响应
        """
        if not isinstance(items, list):
            raise TypeError("Items must be a list")

        processed_items = self._process_success_data(items)
        return self._make_response(
            code=success_status.code,
            data={"items": processed_items, "page": page, "limit": limit, "total": total},
        )

    def error(self, error: AppError, *, message: str = "", lang: str = "zh") -> CustomORJSONResponse:
        """
        通用错误响应。

        Args:
            error: GlobalCodes 中定义的错误对象
            message: 自定义详细信息。如果传入，将拼接到默认文案后面。
            lang: 语言代码 ('zh', 'en')，默认为 'zh'
        """
        # 1. 获取预定义的错误信息 (例如 "请求参数错误")
        base_msg = error.get_message(lang)

        # 2. 拼接逻辑
        if message:
            final_message = f"{base_msg}: {message}"
        else:
            final_message = base_msg

        return self._make_response(code=error.code, message=final_message)


# 全局单例
_response_factory = _ResponseFactory()


# =========================================================
# 4. 工具函数
# =========================================================


def success_response(data: dict | list | BaseModel | None = None) -> CustomORJSONResponse:
    """
    成功响应
    """
    return _response_factory.success(data=data)


def success_list_response(data: list, page: int, limit: int, total: int) -> CustomORJSONResponse:
    """
    分页列表响应
    """
    return _response_factory.list(items=data, page=page, limit=limit, total=total)


def error_response(error: AppError, *, message: str = "", lang: str = "zh") -> CustomORJSONResponse:
    """
    通用错误响应
    """
    return _response_factory.error(error, message=message, lang=lang)


def wrap_sse_data(content: str | dict) -> str:
    """
    将内容包装为 SSE (Server-Sent Events) 格式
    """
    if isinstance(content, dict):
        # 序列化并确保是 utf-8 字符串
        content = orjson_dumps(content)
    return f"data: {content}\n\n"



'''
使用示例
class GlobalCodes(BaseCodes):
    """
    全局状态码定义
    """

    # 客户端错误 (40000 - 49999)
    BadRequest = AppError(40000, {"zh": "请求参数错误", "en": "Bad Request"})
    Unauthorized = AppError(40001, {"zh": "未授权，请登录", "en": "Unauthorized"})
    Forbidden = AppError(40003, {"zh": "权限不足，禁止访问", "en": "Forbidden"})
    NotFound = AppError(40004, {"zh": "资源不存在", "en": "Not Found"})
    PayloadTooLarge = AppError(40005, {"zh": "请求载荷过大", "en": "Payload Too Large"})
    UnprocessableEntity = AppError(40006, {"zh": "无法处理的实体", "en": "Unprocessable Entity"})

    # 服务端错误 (50000 - 59999)
    InternalServerError = AppError(50000, {"zh": "服务器内部错误", "en": "Internal Server Error"})


global_codes = BaseCodes
'''
