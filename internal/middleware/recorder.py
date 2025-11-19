import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from internal.utils.exception import get_last_exec_tb
from pkg.logger_tool import logger
from pkg.resp_tool import error_code, response_factory


class RecordMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4().hex))

        with logger.contextualize(trace_id=trace_id):
            logger.info(
                f"access log, ip={request.client.host}, method={request.method}, path={request.url.path}, params={dict(request.query_params)}")

            start_time = time.perf_counter()
            try:
                response: Response = await call_next(request)
            except Exception as exc:
                logger.error(f"Unhandled exception occurred during request processing, exc={get_last_exec_tb(exc)}")
                return response_factory.response(
                    code=error_code.InternalServerError, message=f"Unhandled Exception: {exc}"
                )
            process_time = time.perf_counter() - start_time

            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-Trace-ID"] = trace_id

            logger.info(f'response log, processing time={process_time:.2f}s')

        return response