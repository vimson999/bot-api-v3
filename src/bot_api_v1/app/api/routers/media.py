from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig
from bot_api_v1.app.utils.decorators.auth_key_checker import require_auth_key
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.schemas import BaseResponse, MediaContentResponse, MediaExtractResponse, RequestContext
from bot_api_v1.app.db.session import get_db
from bot_api_v1.app.services.business.media_service import MediaService, MediaError
from bot_api_v1.app.core.signature import require_signature
from bot_api_v1.app.utils.decorators.auth_feishu_sheet import require_feishu_signature
from bot_api_v1.app.core.context import request_ctx

# 导入请求模型
from pydantic import BaseModel, HttpUrl, validator, Field

class MediaExtractRequest(BaseModel):
    """媒体内容提取请求模型"""
    url: HttpUrl = Field(..., description="媒体URL地址")
    extract_text: bool = Field(True, description="是否提取文案内容")
    include_comments: bool = Field(False, description="是否包含评论数据")
    
    @validator('url')
    def validate_url(cls, v):
        """验证URL格式"""
        if not str(v).startswith(('http://', 'https://')):
            raise ValueError('必须是有效的HTTP或HTTPS URL')
        return str(v)

router = APIRouter(prefix="/media", tags=["媒体服务"])

# 实例化服务
media_service = MediaService()

@router.post(
    "/extract",
    response_model=MediaExtractResponse,
    responses={
        200: {"description": "成功提取媒体内容"},
        400: {"description": "无效的请求参数"},
        404: {"description": "无法找到指定URL的媒体内容"},
        500: {"description": "服务器内部错误"}
    }
)
@TollgateConfig(
    title="提取媒体内容",
    type="media",
    base_tollgate="10",
    current_tollgate="1",
    plat="api"
)
@require_feishu_signature()  # 添加飞书签名验证，测试模式可豁免
@require_auth_key()  # 添加授权密钥验证，测试模式可豁免
async def extract_media_content(
    request: Request,
    extract_request: MediaExtractRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    提取媒体内容信息
    
    - 支持抖音和小红书平台
    - 提取视频基本信息、作者信息、统计数据等
    - 可选择是否提取文案内容
    """
    try:
        # 获取上下文信息用于响应
        trace_key = request_ctx.get_trace_key()
        app_id = request_ctx.get_app_id()
        source = request_ctx.get_source()
        user_id = request_ctx.get_user_id()
        user_name = request_ctx.get_user_name()
        ip_address = request.client.host if hasattr(request, "client") else None
        
        logger.info(
            f"接收媒体提取请求: {extract_request.url}",
            extra={
                "request_id": trace_key,
                "app_id": app_id,
                "source": source,
                "user_id": user_id
            }
        )
        
        # 提取媒体内容
        media_content = await media_service.extract_media_content(
            url=extract_request.url,
            extract_text=extract_request.extract_text,
            include_comments=extract_request.include_comments
        )
        
        # 构建请求上下文数据
        request_context = RequestContext(
            trace_id=trace_key,
            app_id=app_id,
            source=source,
            user_id=user_id,
            user_name=user_name,
            ip=ip_address,
            timestamp=datetime.now()
        )
        
        # 创建响应
        response = MediaExtractResponse(
            code=200,
            message="成功提取媒体内容",
            data=media_content,
            request_context=request_context
        )
        
        return response
        
    except MediaError as e:
        logger.error(f"媒体提取失败: {str(e)}", extra={"request_id": trace_key})
        raise HTTPException(
            status_code=404,
            detail=f"无法提取媒体内容: {str(e)}"
        )
        
    except Exception as e:
        logger.error(f"处理媒体提取请求时发生未知错误: {str(e)}", 
                    exc_info=True, 
                    extra={"request_id": trace_key})
        raise HTTPException(
            status_code=500,
            detail=f"处理请求时发生未知错误: {str(e)}"
        )