import traceback


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