from typing import Annotated

from fastapi import APIRouter, Depends

from internal.services.user import UserService, new_user_service
from pkg.toolkit.response import success_response

router = APIRouter(prefix="/test", tags=["web v1 user"])

UserServiceDep = Annotated[UserService, Depends(new_user_service)]


@router.get("/hello_world")
async def hello_world(service: UserServiceDep):
    await service.hello_world()
    return success_response()
