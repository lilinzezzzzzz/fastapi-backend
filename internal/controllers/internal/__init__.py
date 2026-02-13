from fastapi import APIRouter

from internal.controllers.internal import user

router = APIRouter(prefix="/v1/internal")

routers = [
    user.router,
]

for r in routers:
    router.include_router(r)
