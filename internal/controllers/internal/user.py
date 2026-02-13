from fastapi import APIRouter, Request

from internal.schemas import BaseResponse
from pkg.toolkit.response import success_response

router = APIRouter(prefix="/user", tags=["internal user"])


@router.get("/hello-world", summary="user hello world", response_model=BaseResponse)
def hello_world(request: Request):
    return success_response()
