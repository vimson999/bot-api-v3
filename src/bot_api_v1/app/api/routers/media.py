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
import re

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


async def clean_url(text: str) -> Optional[str]:
    """
    从文本中提取并清理URL地址

    Args:
        text (str): 需要提取URL的文本内容

    Returns:
        Optional[str]: 返回提取出的URL，如果没有找到则返回None
    """
    try:
        if not text:
            logger.warning("收到空的URL文本")
            return None

        # 更全面的URL正则表达式匹配模式
        url_regex = r'https?://(?:[-\w.]|[?=&/%#])+'

        # 执行正则表达式匹配
        matches = re.findall(url_regex, str(text))

        if not matches:
            logger.warning(f"未找到有效的URL: {text}")
            return None

        url = matches[0].strip()
        url = re.sub(r'[<>"{}|\\\'^`]', '', url)

        if not url.startswith(('http://', 'https://')):
            logger.warning(f"URL协议不支持: {url}")
            return None

        return url

    except Exception as e:
        logger.error(f"URL提取失败: {str(e)}", exc_info=True)
        return None

@router.post("/extract", response_model=MediaExtractResponse)
@TollgateConfig(title="提取媒体内容", type="media", base_tollgate="10", current_tollgate="1", plat="api")
@require_feishu_signature()
@require_auth_key()
async def extract_media_content(
    request: Request,
    extract_request: MediaExtractRequest,
    db: AsyncSession = Depends(get_db)
):
    """提取媒体内容信息"""
    # 获取上下文信息
    trace_key = request_ctx.get_trace_key()
    app_id = request_ctx.get_app_id()
    source = request_ctx.get_source()
    user_id = request_ctx.get_user_id()
    user_name = request_ctx.get_user_name()
    ip_address = request.client.host if request.client and hasattr(request.client, "host") else None
    
    try:
        logger.info(
            f"接收媒体提取请求: {extract_request.url}",
            extra={
                "request_id": trace_key,
                "app_id": app_id,
                "source": source,
                "user_id": user_id
            }
        )
        
        # 提取并验证URL
        cleaned_url = await clean_url(extract_request.url)
        if not cleaned_url:
            raise MediaError("无效的URL地址或URL格式不正确")
        
        logger.info(
            f"提取媒体cleaned_url内容: {cleaned_url}",
            extra={"request_id": trace_key}
        )

        # 提取媒体内容
        media_content = await media_service.extract_media_content(
            url=cleaned_url,
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
            data=MediaContentResponse(**media_content) if media_content else None,
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

