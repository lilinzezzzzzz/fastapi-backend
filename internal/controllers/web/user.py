from fastapi import APIRouter, Depends, Request

from internal.services.user import UserService, new_user_service
from pkg.response import success_response

router = APIRouter(prefix="/test", tags=["web v1 user"])


@router.get("/hello_world")
async def hello_world(
    request: Request,
    service: UserService = Depends(UserService),
):
    await service.get_user_by_phone(request)
    return success_response()
