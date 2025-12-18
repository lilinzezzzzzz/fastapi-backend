from fastapi import APIRouter, Request

from internal.services.user import user_svc
from pkg.response import success_response

router = APIRouter(prefix="/test", tags=["web v1 user"])


@router.get("/hello_world")
async def hello_world(request: Request):
    await user_svc.hello(request)
    return success_response()
