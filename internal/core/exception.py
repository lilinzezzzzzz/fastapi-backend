from pkg.toolkit.response import AppError


class AppException(Exception):
    def __init__(self, error: AppError, message: str = ""):
        """
        自定义 HTTP 异常，支持任意状态码，不受 http.HTTPStatus 限制。

        :param error: AppError
        :param message: 详细信息，可以是字符串或字典
        """
        self.error = error
        self.message = message

    def __repr__(self):
        return f"AppException(error={self.error}, message={self.message})"


class GlobalErrors:
    """
    全局状态码定义
    """

    # 客户端错误 (40000 - 49999)
    BadRequest = AppError(40000, {"zh": "请求参数错误", "en": "Bad Request"})
    Unauthorized = AppError(40001, {"zh": "未授权，请登录", "en": "Unauthorized"})
    InvalidSignature = AppError(40002, {"zh": "签名验证失败", "en": "Signature Invalid"})
    Forbidden = AppError(40003, {"zh": "权限不足，禁止访问", "en": "Forbidden"})
    NotFound = AppError(40004, {"zh": "资源不存在", "en": "Not Found"})
    PayloadTooLarge = AppError(40005, {"zh": "请求载荷过大", "en": "Payload Too Large"})
    UnprocessableEntity = AppError(40006, {"zh": "无法处理的实体", "en": "Unprocessable Entity"})

    # 服务端错误 (50000 - 59999)
    InternalServerError = AppError(50000, {"zh": "服务器内部错误", "en": "Internal Server Error"})


errors = GlobalErrors()
