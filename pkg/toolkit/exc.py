import traceback


def _get_last_exec_tb(exc: Exception, lines: int = 5) -> str:
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    last_5_lines = tb_lines[-lines:] if len(tb_lines) >= lines else tb_lines
    return "\n".join(last_5_lines).strip()


def get_business_exec_tb(exc: Exception) -> str:
    return _get_last_exec_tb(exc, lines=3)


def get_unexpected_exec_tb(exc: Exception) -> str:
    return _get_last_exec_tb(exc, lines=10)
