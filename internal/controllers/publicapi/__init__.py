from fastapi import APIRouter

from internal.controllers.publicapi import otel_demo, test

router = APIRouter(prefix="/v1/public")

routers = [test.router, otel_demo.router]

for r in routers:
    router.include_router(r)
