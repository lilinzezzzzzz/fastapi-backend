from fastapi import APIRouter, Request

from pkg.response import response_factory

router = APIRouter(prefix="/user", tags=["internal v1 user"])


@router.get("/hello-world", summary="user hello world")
def hello_world(request: Request) -> dict:
    return response_factory.success()
