
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from bot_api_v1.app.core.schemas import BaseResponse, ErrorCode
from bot_api_v1.app.core.logger import logger

async def http_exception_handler(request: Request, exc: Exception):
    error_type = type(exc).__name__
    
    # 定义常见异常映射
    error_mapping = {
        "RequestValidationError": (ErrorCode.BAD_REQUEST, "请求参数校验失败"),
        "AuthenticationError": (ErrorCode.UNAUTHORIZED, "身份认证失败"),
        "PermissionDeniedError": (ErrorCode.FORBIDDEN, "无权访问该资源"),
        "NotFoundError": (ErrorCode.NOT_FOUND, "请求资源不存在"),
        "ValueError": (ErrorCode.BAD_REQUEST, str(exc))
    }
    
    code, message = error_mapping.get(error_type, 
        (ErrorCode.INTERNAL_ERROR, "服务器内部错误"))
    
    # 记录非5xx错误为WARNING级别
    log_level = logger.warning if code < 500 else logger.error
    log_level(f"{error_type}: {str(exc)}", 
             extra={"path": request.url.path, "error_detail": exc.errors() if hasattr(exc, "errors") else None})
    
    return JSONResponse(
        status_code=code,
        content=BaseResponse(
            code=code,
            message=message,
            data=None
        ).dict()
    )