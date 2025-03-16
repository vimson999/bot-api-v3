from fastapi import APIRouter, Depends
from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig
import os
import time
import torch  # 如果需要检查音频服务

router = APIRouter(tags=["System Monitoring"])

@router.get("/health", 
           response_model=BaseResponse)
@TollgateConfig(
    title="系统健康检查", 
    type="health",
    base_tollgate="10",
    current_tollgate="1",
    plat="system"
)
async def health_check(
    db: AsyncSession = Depends(get_db)  # 异步数据库会话依赖注入
):
    """
    系统健康检查端点，验证各组件状态
    """
    start_time = time.time()
    components = {}
    has_error = False
    
    # 检查数据库连接
    try:
        # 使用 scalar_one_or_none() 替代 fetchone()
        result = await db.scalar(text("SELECT 1"))
        components["database"] = "healthy" if result is not None else "error"
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
        components["audio_service"] = "healthy" if torch.cuda.is_available() else "degraded"
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