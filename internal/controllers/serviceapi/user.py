from fastapi import APIRouter, Request

from pkg.response import success_response

router = APIRouter(prefix="/user", tags=["service v1 user"])


@router.get("", summary="service hello world")
def hello_world(request: Request):
    return success_response()
