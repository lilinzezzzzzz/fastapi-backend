import traceback

from pkg.response import BaseCodes, AppError


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


global_codes = GlobalCodes()


class AppException(Exception):
    def __init__(self, code: int, detail: str = ""):
        """
        自定义 HTTP 异常，支持任意状态码，不受 http.HTTPStatus 限制。

        :param code: HTTP 状态码，可以是标准或非标准
        :param detail: 详细信息，可以是字符串或字典
        """
        self.code = code
        self.detail = detail

    def __str__(self):
        return f"AppException: code={self.code}, detail={self.detail}"


def get_last_exec_tb(exc: Exception, lines: int = 5) -> str:
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    last_5_lines = tb_lines[-lines:] if len(tb_lines) >= lines else tb_lines
    return "\n".join(last_5_lines).strip()
