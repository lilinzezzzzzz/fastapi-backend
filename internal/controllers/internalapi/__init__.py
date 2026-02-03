from fastapi import APIRouter

from internal.controllers.internalapi import user

router = APIRouter(prefix="/v1/internal")

routers = [
    user.router
]

for r in routers:
    router.include_router(r)
