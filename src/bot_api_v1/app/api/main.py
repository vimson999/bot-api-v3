from fastapi import APIRouter
from .routers import health

router = APIRouter()
router.include_router(health.router)