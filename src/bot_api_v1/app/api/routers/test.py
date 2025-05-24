
from hashlib import new
from typing import Dict, Any, Optional, Union # 添加 Union
from datetime import datetime
import uuid
import re
import traceback
from bot_api_v1.app.core.cache import RedisCache
from bot_api_v1.app.services.helper.user_profile_helper import UserProfileHelper
from bot_api_v1.app.services.helper.video_comment_helper import VideoCommentHelper

import httpx
from fastapi import Header

from fastapi import APIRouter, Depends, HTTPException, Request, status, Response ,Body# 导入 Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, HttpUrl, validator, Field
from celery.result import AsyncResult # 导入 AsyncResult

# 核心与上下文
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.schemas import BaseResponse, MediaContentResponse, RequestContext,MediaBasicContentResponse
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.signature import require_signature # 如果还需要同步路径的签名
from bot_api_v1.app.utils.media_extrat_format import Media_extract_format

# 数据库
from bot_api_v1.app.db.session import get_db

# 服务与工具
from bot_api_v1.app.services.business.media_service import MediaService, MediaError # 导入平台
from bot_api_v1.app.constants.media_info import MediaPlatform

from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig
from bot_api_v1.app.utils.decorators.api_refer import require_api_security ,decrypt_and_validate_request
from bot_api_v1.app.utils.decorators.auth_key_checker import require_auth_key
from bot_api_v1.app.utils.decorators.auth_feishu_sheet import require_feishu_signature

# Celery 相关导入
from bot_api_v1.app.tasks.celery_adapter import register_task, get_task_status # 导入适配器函数
from bot_api_v1.app.tasks.celery_tasks import run_media_extraction_new # 导入新的 Celery Task
from bot_api_v1.app.tasks.celery_app import celery_app # 导入 celery_app 实例 (用于 AsyncResult)


class MediaExtractRequest(BaseModel):
    """媒体内容提取请求模型"""
    url: HttpUrl = Field(..., description="媒体URL地址")
    extract_text: bool = Field(True, description="是否提取文案内容")
    include_comments: bool = Field(False, description="是否包含评论数据")

    @validator('url')
    def validate_url(cls, v):
        if not str(v).startswith(('http://', 'https://')):
            raise ValueError('必须是有效的HTTP或HTTPS URL')
        return str(v)

class MediaExtractSubmitResponse(BaseModel):
    """提交异步提取任务后的响应模型"""
    code: int = 202
    message: str
    task_id: str
    root_trace_key: str
    request_context: RequestContext

class MediaExtractResponse(BaseModel): # 复用或重命名旧的响应模型
    """提取媒体内容（同步或完成后）的响应模型"""
    code: int = 200
    message: str
    data: Optional[MediaContentResponse] = None # MediaContentResponse 需已定义
    request_context: RequestContext


class MediaExtractBasicContentResponse(BaseModel): # 复用或重命名旧的响应模型
    """提取媒体内容（同步或完成后）的响应模型"""
    code: int = 200
    message: str
    data: Optional[MediaBasicContentResponse] = None # MediaContentResponse 需已定义
    request_context: RequestContext

class MediaExtractStatusResponse(BaseModel):
    """查询异步提取任务状态的响应模型"""
    code: int
    message: str
    task_id: str
    root_trace_key: str
    status: str # PENDING, running, completed, failed, cancelled, ...
    result: Optional[MediaContentResponse] = None # 任务成功时的结果
    data: Optional[MediaContentResponse] = None # MediaContentResponse 需已定义
    error: Optional[str] = None # 任务失败时的错误信息
    request_context: RequestContext

router = APIRouter(prefix="/tt", tags=["test服务"])

# 实例化服务 (如果还需要调用 identify_platform 或 extract_text=False 的逻辑)
media_service = MediaService()
media_extract_format = Media_extract_format() # 实例化 Media_extract_format
user_profile_helper = UserProfileHelper()
video_comment_helper = VideoCommentHelper()




@router.post("/upro", response_model=BaseResponse)
# @TollgateConfig(title="获取用户主页信息", type="media", base_tollgate="10", current_tollgate="1", plat="api")
# @require_feishu_signature()
# @require_auth_key()
async def get_user_profile_api(
    req: Request
):
    """
    获取用户主页信息
    """
    try:
        cq_data = await req.json()
        user_url = str(cq_data.get("url"))
        result = await user_profile_helper.get_user_profile_logic(user_url)

        return BaseResponse(code=200, message="获取成功", data=result)
    except Exception as e:
        # 这里建议日志也交由 helper 处理，或保留原有日志
        return BaseResponse(code=500, message=f"获取失败: {str(e)}")




@router.post("/vcl", response_model=BaseResponse)
# @TollgateConfig(title="获取视频评论列表", type="media", base_tollgate="10", current_tollgate="1", plat="api")
# @require_feishu_signature()
# @require_auth_key()
async def get_video_comment_list_api(
    req: Request
):
    try:
        cq_data = await req.json()
        video_url = str(cq_data.get("url"))
        result = await video_comment_helper.get_video_comment_list(video_url)

        return BaseResponse(code=200, message="获取成功", data=result)
    except Exception as e:
        # 这里建议日志也交由 helper 处理，或保留原有日志
        return BaseResponse(code=500, message=f"获取失败: {str(e)}")