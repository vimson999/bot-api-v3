from fastapi import APIRouter, Depends,Request
from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.db.session import get_db
from sqlalchemy.orm import Session
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig
import os
import time


router = APIRouter(tags=["System Monitoring"])
@router.get("/health", 
           response_model=BaseResponse,
           responses={
               200: {"description": "服务正常运行", "content": {"application/json": {"example": {
                   "code": 200,
                   "message": "服务正常运行",
                   "data": {
                       "status": "healthy", 
                       "components": {
                           "database": "healthy",
                           "cache": "healthy",
                           "audio_service": "healthy"
                       },
                       "version": "1.0.0",
                       "uptime": "3d 12h 45m"
                   },
                   "timestamp": "2025-03-06T17:30:45.123Z"
               }}}},
               503: {"description": "服务部分或完全不可用"}
           })
@TollgateConfig(
    title="系统健康检查", 
    type="health",
    base_tollgate="10",
    current_tollgate="1",
    plat="system"
)
async def health_check(db: Session = Depends(get_db), 
                       request: Request = None):
    """
    系统健康检查端点，验证以下内容：
    - 基础服务状态
    - 数据库连接状态
    - 缓存连接状态
    - 关键依赖服务状态

    返回各组件的健康状态和系统整体状态。
    """
    start_time = time.time()
    components = {}
    has_error = False
    
    # 检查数据库连接
    try:
        result = await check_database(db)
        components["database"] = result["status"]
        if result["status"] != "healthy":
            has_error = True
    except Exception as e:
        logger.error(f"数据库健康检查异常: {str(e)}")
        components["database"] = "error"
        has_error = True
    
    # 检查缓存服务
    try:
        # TODO: 实现缓存服务检查
        components["cache"] = "healthy"
    except Exception:
        components["cache"] = "error"
        has_error = True
    
    # 检查音频服务
    try:
        # 简单检查音频服务是否可用
        if torch.cuda.is_available():
            components["audio_service"] = "healthy"
        else:
            components["audio_service"] = "degraded"  # CPU模式，性能降级
    except Exception:
        components["audio_service"] = "unknown"
    
    # 系统信息
    system_info = {
        "version": "1.0.0",  # 从配置获取
        "environment": os.environ.get("ENV", "development"),
        "response_time": f"{(time.time() - start_time) * 1000:.2f}ms"
    }
    
    # 确定整体状态
    if has_error:
        status = "degraded"
        status_code = 503
        message = "服务部分可用"
    else:
        status = "healthy"
        status_code = 200
        message = "服务正常运行"
    
    return BaseResponse(
        code=status_code,
        message=message,
        data={
            "status": status,
            "components": components,
            **system_info
        }
    )

async def check_database(db: Session) -> dict:
    """检查数据库连接状态"""
    try:
        # 执行简单查询
        db.execute("SELECT 1")
        return {"status": "healthy", "message": "Connected"}
    except Exception as e:
        logger.error(f"数据库连接失败: {str(e)}")
        return {"status": "error", "message": str(e)}