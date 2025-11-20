import traceback


class AppException(Exception):
    def __init__(self, code: int, detail: str = "", headers: dict | None = None):
        """
        自定义 HTTP 异常，支持任意状态码，不受 http.HTTPStatus 限制。

        :param code: HTTP 状态码，可以是标准或非标准
        :param detail: 详细信息，可以是字符串或字典
        :param headers: 可选的 HTTP 头
        """
        self.code = code
        self.detail = detail
        self.headers = headers


def get_last_exec_tb(exc: Exception, lines: int = 3) -> str:
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    last_5_lines = tb_lines[-lines:] if len(tb_lines) >= lines else tb_lines
    return "\n".join(last_5_lines).strip()