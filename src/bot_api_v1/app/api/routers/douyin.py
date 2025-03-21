# src/bot_api_v1/app/api/routers/douyin.py
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig
from bot_api_v1.app.utils.decorators.auth_key_checker import require_auth_key
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.db.session import get_db
from bot_api_v1.app.services.business.douyin_service import DouyinService, DouyinError
from bot_api_v1.app.core.signature import require_signature
from bot_api_v1.app.utils.decorators.auth_feishu_sheet import require_feishu_signature

router = APIRouter(prefix="/douyin", tags=["抖音服务"])

# 实例化服务
douyin_service = DouyinService()

from pydantic import BaseModel, HttpUrl, validator, Field

# 视频信息请求模型
class VideoInfoRequest(BaseModel):
    """抖音视频信息请求模型"""
    url: HttpUrl
    extract_text: bool = Field(False, description="是否提取视频文案")
    
    @validator('url')
    def validate_url(cls, v):
        """验证URL格式"""
        if not str(v).startswith(('http://', 'https://')):
            raise ValueError('必须是有效的HTTP或HTTPS URL')
        return str(v)

# 用户信息请求模型 - 这在原始代码中缺失
class UserInfoRequest(BaseModel):
    """抖音用户信息请求模型"""
    user_id: str = Field(..., description="抖音用户ID或sec_uid")

# 视频信息API
@router.post(
    "/video/info",
    response_model=BaseResponse,
    responses={
        200: {"description": "成功获取视频信息"},
        400: {"description": "无效的请求参数"},
        404: {"description": "无法找到指定URL的视频"},
        500: {"description": "服务器内部错误"}
    }
)
@TollgateConfig(
    title="获取抖音视频信息",
    type="douyin_video_info",
    base_tollgate="20",
    current_tollgate="1",
    plat="api"
)
@require_feishu_signature(exempt=True)  # 飞书签名验证 - 添加豁免选项方便测试
@require_auth_key(exempt=True)  # 授权密钥验证 - 添加豁免选项方便测试
async def get_video_info(
    request: VideoInfoRequest,
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    获取抖音视频信息
    
    - 返回视频的详细信息，包括标题、作者、点赞数等
    - 需要提供有效的抖音视频URL
    - 可以选择是否同时提取视频文案（会增加处理时间）
    """
    try:
        # 获取视频信息，传入extract_text参数
        video_info = await douyin_service.get_video_info(
            request.url, 
            extract_text=request.extract_text
        )
        
        return BaseResponse(
            code=200,
            message="成功获取抖音视频信息",
            data=video_info
        )
        
    except DouyinError as e:
        logger.error(f"获取抖音视频信息失败: {str(e)}")
        raise HTTPException(
            status_code=404,
            detail=f"无法获取抖音视频信息: {str(e)}"
        )
        
    except Exception as e:
        logger.error(f"处理抖音视频信息请求时发生未知错误: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"处理请求时发生未知错误: {str(e)}"
        )

# 用户信息API
@router.post(
    "/user/info",
    response_model=BaseResponse,
    responses={
        200: {"description": "成功获取用户信息"},
        400: {"description": "无效的请求参数"},
        404: {"description": "无法找到指定ID的用户"},
        500: {"description": "服务器内部错误"}
    }
)
@TollgateConfig(
    title="获取抖音用户信息",
    type="douyin",
    base_tollgate="10",
    current_tollgate="1",
    plat="api"
)
@require_feishu_signature(exempt=True)  # 添加豁免选项方便测试
@require_auth_key(exempt=True)  # 添加豁免选项方便测试
async def get_user_info(
    request: UserInfoRequest,
    req: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    获取抖音用户信息
    
    - 返回用户的详细信息，包括昵称、关注数、粉丝数等
    - 需要提供有效的抖音用户ID或sec_uid
    """
    try:
        # 获取用户信息
        user_info = await douyin_service.get_user_info(request.user_id)
        
        return BaseResponse(
            code=200,
            message="成功获取抖音用户信息",
            data=user_info
        )
        
    except DouyinError as e:
        logger.error(f"获取抖音用户信息失败: {str(e)}")
        raise HTTPException(
            status_code=404,
            detail=f"无法获取抖音用户信息: {str(e)}"
        )
        
    except Exception as e:
        logger.error(f"处理抖音用户信息请求时发生未知错误: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"处理请求时发生未知错误: {str(e)}"
        )