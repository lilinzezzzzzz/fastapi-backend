"""自定义异常类"""


class AppException(Exception):
    def __init__(self, error, message: str = ""):
        """
        自定义 HTTP 异常，支持任意状态码，不受 http.HTTPStatus 限制。

        :param error: AppError
        :param message: 详细信息，可以是字符串或字典
        """
        self.error = error
        self.message = message

    def __repr__(self):
        return f"AppException(error={self.error}, message={self.message})"
