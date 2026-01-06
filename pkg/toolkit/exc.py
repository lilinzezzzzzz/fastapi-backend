import traceback


def get_last_exec_tb(exc: Exception, lines: int = 5) -> str:
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    last_5_lines = tb_lines[-lines:] if len(tb_lines) >= lines else tb_lines
    return "\n".join(last_5_lines).strip()
