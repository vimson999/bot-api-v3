from fastapi import APIRouter, Depends
from bot_api_v1.app.db.session import check_db_connection
from bot_api_v1.app.core.config import settings

router = APIRouter()

@router.get("/info", tags=["system"])
async def system_info():
    """返回系统信息"""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }

@router.get("/health/db", tags=["system"])
async def db_health_check():
    """检查数据库健康状况"""
    is_healthy = await check_db_connection()
    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "component": "database"
    }
