#main.py
from fastapi import APIRouter
from .routers import health
from .routers import script
from .routers import douyin  # 导入新的抖音路由
from .routers import media  # 导入新的媒体路由
from .routers import monitoring  # 导入监控路由
from .routers import points  # 导入积分路由



# from bot_api_v1.app.core.logger import setup_logger

router = APIRouter()
router.include_router(health.router)
router.include_router(script.router)
router.include_router(douyin.router)  # 注册抖音路由
router.include_router(media.router)  # 注册媒体路由
router.include_router(monitoring.router, prefix="/monitoring")  # 注册监控路由
router.include_router(points.router)  # 注册积分路由

# logger = setup_logger()