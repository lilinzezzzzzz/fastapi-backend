from typing import Annotated

from fastapi import APIRouter, Depends

from internal.services.user import UserService, new_user_service
from pkg.toolkit.response import success_response

router = APIRouter(prefix="/user", tags=["api user"])

UserServiceDep = Annotated[UserService, Depends(new_user_service)]


@router.get("/hello-world", summary="用户 Hello World")
async def hello_world(service: UserServiceDep):
    await service.hello_world()
    return success_response()
