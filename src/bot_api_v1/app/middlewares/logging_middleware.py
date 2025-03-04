# logging_middleware.py
import time
import uuid
import os
from fastapi import Request
from starlette.responses import Response  # 新增的导入
from bot_api_v1.app.core.logger import logger

async def log_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    # 记录请求信息
    logger.info(
        "Request | Method=%s Path=%s",
        request.method,
        request.url.path,
        extra={
            "request_id": request_id,
            "headers": dict(request.headers)
        }
    )

    # 处理请求
    try:
        response = await call_next(request)
        
        # 克隆响应体
        resp_body = []
        async for chunk in response.body_iterator:
            resp_body.append(chunk)
        content = b''.join(resp_body)
        
        # 记录响应内容（安全处理）
        try:
            log_content = content.decode(errors='replace')[:500]  # 限制长度
        except Exception as e:
            log_content = f"<解码失败: {str(e)}>"

        logger.debug(
            "Response Content | Status=%d Size=%d\n%s",
            response.status_code,
            len(content),
            log_content,
            extra={"request_id": request_id}
        )
        
        # 重建响应
        return Response(
            content=content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type
        )
    
    except Exception as e:
        status_code = 500
        logger.error(
            "Request Error: %s", str(e),
            extra={"request_id": request_id},
            exc_info=True
        )
        raise
    
    finally:
        process_time = (time.time() - start_time) * 1000
        logger.info(
            "Response | Status=%d Duration=%.2fms",
            response.status_code,
            process_time,
            extra={
                "request_id": request_id,
                "headers": dict(response.headers)
            }
        )
    
    return response