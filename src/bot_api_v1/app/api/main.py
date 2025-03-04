#main.py
from fastapi import APIRouter
from .routers import health
# from bot_api_v1.app.core.logger import setup_logger

router = APIRouter()
router.include_router(health.router)

# logger = setup_logger()