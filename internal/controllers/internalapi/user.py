from fastapi import APIRouter, Request

from pkg.toolkit.response import success_response

router = APIRouter(prefix="/user", tags=["internal v1 user"])


@router.get("/hello-world", summary="user hello world")
def hello_world(request: Request):
    return success_response()
