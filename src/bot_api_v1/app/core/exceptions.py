from fastapi import Request, status
from fastapi.responses import JSONResponse
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class CustomException(Exception):
    """自定义异常基类，用于标准化API错误响应"""
    
    def __init__(
        self, 
        status_code: int = 400, 
        message: str = "Bad request", 
        code: str = "error", 
        details: Optional[Dict[str, Any]] = None
    ):
        self.status_code = status_code
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    全局异常处理器，将各种异常转换为标准的JSON响应
    """
    # 获取请求ID，如果在headers中有的话
    request_id = getattr(request.state, "request_id", "unknown")
    
    # 判断是否为自定义异常
    if isinstance(exc, CustomException):
        # 记录自定义异常
        logger.warning(
            f"Request failed: {exc.message}",
            extra={"request_id": request_id}
        )
        
        # 返回标准化响应
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
            },
        )
    
    # 处理未预期的异常
    logger.exception(
        f"Unhandled exception: {str(exc)}",
        extra={"request_id": request_id}
    )
    
    # 返回通用服务器错误
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "internal_error",
            "message": "An internal server error occurred",
            "details": {"error": str(exc)} if not isinstance(exc, Exception) else {},
            "request_id": request_id,
        },
    )
