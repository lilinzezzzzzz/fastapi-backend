from fastapi import APIRouter

from internal.services.user import user_service
from pkg.response import success_response

router = APIRouter(prefix="/test", tags=["web v1 user"])


@router.get("/hello_world")
async def hello_world():
    await user_service.hello_world()
    return success_response()
