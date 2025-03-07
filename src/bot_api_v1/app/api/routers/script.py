"""
音频转写脚本处理相关API路由
"""
from typing import Dict, Any, Optional
import os
import time
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, HttpUrl, validator
from sqlalchemy.orm import Session

from bot_api_v1.app.core.decorators import TollgateConfig
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.db.session import get_db
from bot_api_v1.app.services.script_service import ScriptService, AudioDownloadError, AudioTranscriptionError

router = APIRouter(prefix="/script", tags=["脚本服务"])

# 实例化服务
script_service = ScriptService()


class ScriptRequest(BaseModel):
    """音频转文本请求模型"""
    url: HttpUrl = Query(..., description="音频来源URL，支持YouTube、Bilibili等平台")
    
    @validator('url')
    def validate_url(cls, v):
        """验证URL格式"""
        if not str(v).startswith(('http://', 'https://')):
            raise ValueError('必须是有效的HTTP或HTTPS URL')
        return str(v)


class ScriptResponse(BaseModel):
    """音频转文本响应模型"""
    text: str
    title: Optional[str] = None
    source_url: str


@router.post(
    "/transcribe",
    response_model=BaseResponse[ScriptResponse],
    responses={
        200: {
            "description": "成功将音频转写为文本",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "message": "成功",
                        "data": {
                            "text": "这是转写后的文本内容...",
                            "title": "示例音频标题",
                            "source_url": "https://example.com/audio"
                        },
                        "timestamp": "2025-03-06T17:30:45.123Z"
                    }
                }
            }
        },
        400: {"description": "无效的请求参数"},
        404: {"description": "无法找到或下载指定URL的音频"},
        500: {"description": "服务器内部错误"}
    }
)
@TollgateConfig(
    title="音频转写",
    type="script",
    base_tollgate="10",
    current_tollgate="1",
    plat="api"
)
async def transcribe_audio(
    request: ScriptRequest,
    db: Session = Depends(get_db)
):
    """
    将URL指向的音频文件转写为文本
    
    - 支持多种音频来源，包括YouTube、Bilibili等平台
    - 自动处理长音频，分段转写提高效率
    - 返回完整的转写文本及相关元数据
    """
    try:
        # 下载音频
        audio_path, audio_title = await script_service.download_audio(request.url)
        
        # 转写音频
        transcribed_text = await script_service.transcribe_audio(audio_path)
        
        # 构造响应
        result = ScriptResponse(
            text=transcribed_text,
            title=audio_title,
            source_url=str(request.url)
        )
        
        return BaseResponse(
            code=200,
            message="音频转写成功",
            data=result
        )
        
    except AudioDownloadError as e:
        logger.error(f"音频下载失败: {str(e)}")
        raise HTTPException(
            status_code=404,
            detail=f"无法下载指定URL的音频: {str(e)}"
        )
        
    except AudioTranscriptionError as e:
        logger.error(f"音频转写失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"音频转写过程中发生错误: {str(e)}"
        )
        
    except Exception as e:
        logger.error(f"处理音频转写请求时发生未知错误: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"处理请求时发生未知错误: {str(e)}"
        )