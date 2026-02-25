from fastapi import APIRouter

router = APIRouter(prefix="/v1/internal")

routers = []

for r in routers:
    router.include_router(router=r)
