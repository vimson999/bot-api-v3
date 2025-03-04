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
    
    # 安全获取请求头
    try:
        headers_dict = dict(request.headers.items())
    except Exception:
        headers_dict = {"info": "Unable to parse headers"}
    
    # 记录请求信息
    logger.info(
        "Request | Method=%s Path=%s",
        request.method,
        request.url.path,
        extra={
            "request_id": request_id,
            "headers": headers_dict
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

        # 安全获取响应头
        try:
            response_headers = dict(response.headers.items())
        except Exception:
            response_headers = {"info": "Unable to parse response headers"}

        logger.debug(
            "Response Content | Status=%d Size=%d\n%s",
            response.status_code,
            len(content),
            log_content,
            extra={
                "request_id": request_id,
                "headers": response_headers
            }  # 添加响应头到调试日志
        )
        
        # 重建响应
        new_response = Response(
            content=content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type
        )
        
        # 计算处理时间
        process_time = (time.time() - start_time) * 1000
        
        # 记录响应信息
        logger.info(
            "Response | Status=%d Duration=%.2fms",
            response.status_code,
            process_time,
            extra={
                "request_id": request_id,
                "headers": response_headers
            }
        )
        
        return new_response
    
    except Exception as e:
        # 异常处理
        logger.error(
            "Request Error: %s", str(e),
            extra={"request_id": request_id},
            exc_info=True
        )
        # 计算处理时间，即使有异常
        process_time = (time.time() - start_time) * 1000
        logger.info(
            "Response | Status=500 Duration=%.2fms",
            process_time,
            extra={
                "request_id": request_id,
                "headers": {"error": "Exception occurred"}
            }
        )
        raise


# async def log_middleware(request: Request, call_next):
#     request_id = str(uuid.uuid4())
#     start_time = time.time()
    
#     # 记录请求信息
#     logger.info(
#         "Request | Method=%s Path=%s",
#         request.method,
#         request.url.path,
#         extra={
#             "request_id": request_id,
#             "headers": dict(request.headers)
#         }
#     )

#     # 处理请求
#     try:
#         response = await call_next(request)
        
#         # 克隆响应体
#         resp_body = []
#         async for chunk in response.body_iterator:
#             resp_body.append(chunk)
#         content = b''.join(resp_body)
        
#         # 记录响应内容（安全处理）
#         try:
#             log_content = content.decode(errors='replace')[:500]  # 限制长度
#         except Exception as e:
#             log_content = f"<解码失败: {str(e)}>"

#         logger.debug(
#             "Response Content | Status=%d Size=%d\n%s",
#             response.status_code,
#             len(content),
#             log_content,
#             extra={"request_id": request_id}
#         )
        
#         # 重建响应
#         return Response(
#             content=content,
#             status_code=response.status_code,
#             headers=dict(response.headers),
#             media_type=response.media_type
#         )
    
#     except Exception as e:
#         status_code = 500
#         logger.error(
#             "Request Error: %s", str(e),
#             extra={"request_id": request_id},
#             exc_info=True
#         )
#         raise
    
#     finally:
#         process_time = (time.time() - start_time) * 1000
#         logger.info(
#             "Response | Status=%d Duration=%.2fms",
#             response.status_code,
#             process_time,
#             extra={
#                 "request_id": request_id,
#                 "headers": dict(response.headers)
#             }
#         )
    
#     return response