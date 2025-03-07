"""
音频转写脚本处理相关API路由
"""
from typing import Dict, Any, Optional
import os
import time
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from pydantic import BaseModel, HttpUrl, validator
from sqlalchemy.orm import Session

from bot_api_v1.app.core.decorators import TollgateConfig
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.db.session import get_db
from bot_api_v1.app.services.script_service import ScriptService, AudioDownloadError, AudioTranscriptionError
from bot_api_v1.app.core.signature import require_signature

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
                        "timestamp": "2025-03-07T17:30:45.123Z"
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
    type="transcription",
    base_tollgate="20",
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


# 添加一个测试验签的接口
class TestSignatureRequest(BaseModel):
    """测试验签请求模型"""
    message: str = Body(..., description="测试消息")
    timestamp: Optional[int] = Body(None, description="时间戳，可选")


@router.post(
    "/test_signature",
    response_model=BaseResponse,
    responses={
        200: {"description": "验签成功"},
        401: {"description": "验签失败"},
        500: {"description": "服务器内部错误"}
    }
)
@TollgateConfig(
    title="验签测试",
    type="test",
    base_tollgate="30",
    current_tollgate="1",
    plat="api"
)
@require_signature(sign_type="hmac_sha256")  # 应用验签装饰器，使用HMAC-SHA256算法
async def test_signature(
    request: Request,
    data: TestSignatureRequest,
    db: Session = Depends(get_db)
):
    """
    测试签名验证功能
    
    此接口需要通过签名验证才能访问。客户端需要：
    1. 设置X-App-ID请求头，提供应用ID
    2. 设置X-Signature请求头，提供签名
    3. 可选：设置X-Timestamp请求头，提供时间戳
    """
    # 如果代码执行到这里，说明验签已通过
    app_id = request.state.app_id
    
    return BaseResponse(
        code=200,
        message="验签成功",
        data={
            "app_id": app_id,
            "message": data.message,
            "timestamp": data.timestamp or int(time.time())
        }
    )


# 添加一个免验签的测试接口，用于对比
@router.post(
    "/test_no_signature",
    response_model=BaseResponse
)
@TollgateConfig(
    title="免验签测试",
    type="test",
    base_tollgate="30",
    current_tollgate="2",
    plat="api"
)
@require_signature(exempt=True)  # 豁免验签
async def test_no_signature(
    data: TestSignatureRequest
):
    """
    测试免验签功能
    
    此接口不需要签名验证即可访问。
    """
    return BaseResponse(
        code=200,
        message="无需验签",
        data={
            "message": data.message,
            "timestamp": data.timestamp or int(time.time())
        }
    )