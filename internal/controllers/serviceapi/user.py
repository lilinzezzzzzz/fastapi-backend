from fastapi import APIRouter, Depends, Request

from internal.services.user import UserService
from pkg.response import success_response

router = APIRouter(prefix="/user", tags=["service v1 user"])


@router.get("", summary="service hello world")
def hello_world(
    request: Request,
    service: UserService = Depends(UserService),
):
    return success_response()
