from functools import wraps
from typing import Callable, Any

from fastapi import Request, HTTPException
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.schemas import BaseResponse


def require_feishu_signature(exempt: bool = False):
    """
    飞书签名验证装饰器
    
    Args:
        exempt: 是否豁免验证，设为True时跳过验证（主要用于测试）
    
    用法:
        @router.post("/api/endpoint")
        @require_feishu_signature()
        async def endpoint(request: Request):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 首先尝试从参数中获取Request对象
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            for value in kwargs.values():
                if isinstance(value, Request):
                    request = value
                    break
            
            # 如果没有找到Request对象
            if not request:
                logger.error("无法获取请求对象")
                if not exempt:
                    return BaseResponse(
                        code=400,
                        message="无法验证请求",
                        data=None
                    )
                return await func(*args, **kwargs)
            
            # 获取跟踪ID
            trace_key = request_ctx.get_trace_key()
            
            # 从请求头获取飞书签名
            base_signature = request.headers.get("x-base-signature")
            
            # 如果豁免验证或签名存在
            if exempt:
                return await func(*args, **kwargs)
            
            # 如果没有签名
            if not base_signature:
                logger.warning(
                    "缺少飞书签名",
                    extra={"request_id": trace_key}
                )
                return BaseResponse(
                    code=401,
                    message="缺少飞书签名验证信息",
                    data=None
                )
            
            # 使用飞书签名验证模块验证签名
            from bot_api_v1.app.security.signature.providers.feishu_sheet import verify_feishu_token
            
            try:
                valid, token_data = verify_feishu_token(base_signature, debug=True)
                
                # 如果签名验证失败
                if not valid:
                    logger.warning(
                        "飞书签名验证失败",
                        extra={
                            "request_id": trace_key,
                            "signature": base_signature
                        }
                    )
                    return BaseResponse(
                        code=401,
                        message="飞书签名验证失败",
                        data=None
                    )
                
                # 获取token中的packID
                verified_pack_id = token_data.get('packID')

                from bot_api_v1.app.core.config import settings
                # 检查packID是否在允许列表中
                if not verified_pack_id or verified_pack_id not in settings.ALLOWED_FEISHU_PACK_IDS:
                    logger.warning(
                        f"{verified_pack_id}----packID验证失败：不在允许列表中",
                        extra={
                            "request_id": trace_key,
                            "verified_pack_id": verified_pack_id,
                            "allowed_pack_ids": settings.ALLOWED_FEISHU_PACK_IDS
                        }
                    )
                
                # 签名验证成功，记录token信息
                logger.info_to_db(
                    f"飞书签名验证成功，并且流量识别成功，go-on，data is {token_data}",
                    extra={
                        "request_id": trace_key,
                        "token_data": token_data
                    }
                )
                
                # 将验证成功的token数据存储在request状态中，供后续使用
                request.state.feishu_token_data = token_data
                
                # 执行原始函数
                return await func(*args, **kwargs)
            
            except Exception as e:
                logger.error(
                    f"飞书签名验证发生异常: {str(e)}",
                    extra={
                        "request_id": trace_key,
                        "signature": base_signature
                    },
                    exc_info=True
                )
                return BaseResponse(
                    code=500,
                    message="签名验证过程中发生内部错误",
                    data=None
                )
        
        return wrapper
    
    return decorator