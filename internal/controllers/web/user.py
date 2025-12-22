from typing import Annotated

from fastapi import APIRouter, Depends, Request

from internal.services.user import UserService, new_user_service
from pkg.response import success_response

router = APIRouter(prefix="/test", tags=["web v1 user"])


@router.get("/hello_world")
async def hello_world(
    _: Request,
    service: Annotated[UserService, Depends(new_user_service)],
):
    await service.hello_world()
    return success_response()
