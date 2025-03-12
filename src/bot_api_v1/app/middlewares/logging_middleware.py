# bot_api_v1/app/middlewares/logging_middleware.py

import time
import uuid
import json
import io
from fastapi import Request
from starlette.responses import Response
from starlette.routing import Match
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.services.log_service import LogService
import asyncio
from asyncio import create_task
from bot_api_v1.app.core.decorators import get_tollgate_config
from bot_api_v1.app.core.context import request_ctx
from datetime import datetime


# 创建一个全局的任务跟踪器
_TASK_REGISTRY = set()

async def log_middleware(request: Request, call_next):
    # 生成唯一追踪ID
    trace_key = str(uuid.uuid4())
    start_time = time.time()

    # 安全获取请求头
    try:
        headers_dict = dict(request.headers.items())
        # 移除可能的敏感信息（如果有sanitize_headers函数）
        if 'sanitize_headers' in globals():
            sanitized_headers = sanitize_headers(headers_dict)
        else:
            sanitized_headers = {k: v for k, v in headers_dict.items() if not k.lower().startswith('authorization')}
    except Exception:
        headers_dict = {}
        sanitized_headers = {"info": "Unable to parse headers"}
    
    # 尝试获取客户端IP
    client_ip = request.client.host if request.client else None
    
    # 提取请求路径作为方法名
    method_name = f"{request.method}:{request.url.path}"
    
    # 提取用户信息 - 保留原始变量名
    app_id = headers_dict.get('x-app-id', headers_dict.get('X-App-Id'))
    source_info = headers_dict.get('x-source', headers_dict.get('X-Source', 'api'))
    user_uuid = headers_dict.get('x-user-uuid', headers_dict.get('X-User-Uuid'))
    user_nickName = headers_dict.get('x-user-nickname', headers_dict.get('X-User-Nickname'))
    
    # 解决用户昵称的中文乱码问题
    try:
        if isinstance(user_nickName, bytes):
            user_nickName = user_nickName.decode('utf-8')
        elif user_nickName and isinstance(user_nickName, str):
            # 尝试解决乱码
            user_nickName = user_nickName.encode('latin1').decode('utf-8')
    except Exception:
        user_nickName = '-'
    
    # 构建上下文数据
    context_data = {
        'trace_key': trace_key,
        'method_name': method_name,
        'source': source_info,
        'app_id': app_id,
        'user_id': user_uuid,
        'user_name': user_nickName,
        'ip_address': client_ip,
        'request_time': datetime.now().isoformat(),
    }
    
    # 设置上下文
    request_ctx.set_context(context_data)
    
    # 尝试识别路由处理函数并获取tollgate配置
    route_handler = None
    tollgate_config = {}
    
    try:
        for route in request.app.routes:
            match, scope = route.matches({"type": "http", "path": request.url.path, "method": request.method})
            if match != Match.NONE:
                route_handler = route.endpoint
                break
        
        if route_handler:
            # 获取tollgate配置
            tollgate_config = get_tollgate_config(route_handler)
    except Exception as e:
        logger.warning(f"Unable to extract route handler: {str(e)}")
    
    # 根据TollgateConfig配置更新日志参数
    if tollgate_config:
        if 'plat' in tollgate_config and tollgate_config['plat'] and not source_info:
            source_info = tollgate_config['plat']
        
        # 构造tollgate标识
        if 'base_tollgate' in tollgate_config and 'current_tollgate' in tollgate_config:
            log_tollgate = f"{tollgate_config['base_tollgate']}-{tollgate_config['current_tollgate']}"
        else:
            log_tollgate = "10-1"
        
        # 构造备注信息
        if 'title' in tollgate_config and tollgate_config['title']:
            title_prefix = f"[{tollgate_config['title']}] "
            log_memo = title_prefix + "Request"
        else:
            log_memo = "Request"
    else:
        log_tollgate = "10-1"
        log_memo = "Request"
    
    # 存储原始请求体
    request_body = None
    
    # 在请求开始前记录日志
    try:
        # 安全获取请求参数
        query_params = dict(request.query_params)
        
        # 对于POST/PUT/PATCH请求，尝试获取请求体
        if request.method in ["POST", "PUT", "PATCH"]:
            # 使用标准API安全地获取请求体
            body = await request.body()
            
            # 保存原始请求体供后续使用
            body_bytes = io.BytesIO(body)
            
            # 尝试解析JSON
            try:
                # 限制大小
                if len(body) < 10000:  # 约10KB
                    request_body = json.loads(body)
                else:
                    request_body = {"warning": "Body too large to log", "size": len(body)}
            except:
                if len(body) < 1000:  # 只记录小体积的非JSON内容
                    request_body = {"raw": body.decode("utf-8", errors="replace")}
                else:
                    request_body = {"warning": "Non-JSON body too large to log", "size": len(body)}
            
            # 创建请求体副本
            async def receive():
                return {"type": "http.request", "body": body_bytes.read(), "more_body": False}
            
            # 替换请求的_receive方法，确保下游处理程序可以读取请求体
            request._receive = receive
        
        # 启动异步任务记录请求日志并添加到注册表
        task = create_task(
            LogService.save_log(
                trace_key=trace_key,
                method_name=method_name,
                source=source_info,
                app_id=app_id,
                user_uuid=user_uuid,
                user_nickname=user_nickName,
                entity_id=request.query_params.get("entity_id"),
                type=tollgate_config.get("type", "request"),  # 使用装饰器中的type，默认为request
                tollgate=log_tollgate,
                level="info",
                para=query_params,
                header=sanitized_headers,
                body=request_body,
                memo=log_memo,
                ip_address=client_ip
            )
        )
        register_task(task)
        
    except Exception as e:
        logger.error(f"Failed to log request to database: {str(e)}", exc_info=True)
    
    # # 记录请求信息到文本日志
    logger.info(
        f"Request | Method={request.method} Path={request.url.path}",
        extra={
            "request_id": trace_key,
            "headers": sanitized_headers
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
            # 限制大小避免大量日志
            if len(content) < 10000:  # 约10KB
                log_content = content.decode(errors='replace')
            else:
                log_content = f"<Content too large: {len(content)} bytes>"
        except Exception as e:
            log_content = f"<解码失败: {str(e)}>"

        # 安全获取响应头
        try:
            response_headers = dict(response.headers.items())
            sanitized_response_headers = sanitize_headers(response_headers)
        except Exception:
            sanitized_response_headers = {"info": "Unable to parse response headers"}

        # 记录响应日志到文本
        logger.debug(
            "Response Content | Status=%d Size=%d\n%s",
            response.status_code,
            len(content),
            log_content[:500],  # 只记录前500个字符
            extra={
                "request_id": trace_key,
                "headers": sanitized_response_headers
            }
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

        # 记录响应信息到文本日志
        logger.info(
            "Response | Status=%d Duration=%.2fms" % (response.status_code, process_time),
            extra={
                "request_id": trace_key,
                "headers": sanitized_response_headers
            }
        )
        
        # 更新响应tollgate和备注
        if tollgate_config:
            base_gate = tollgate_config.get("base_tollgate", "1")
            current_gate = base_gate  # 响应阶段+1
            response_tollgate = f'{base_gate}-{base_gate}'
            
            title = tollgate_config.get("title", "")
            response_memo = f"[{title}] Duration: {process_time:.2f}ms, Status: {response.status_code}" if title else f"Duration: {process_time:.2f}ms, Status: {response.status_code}"
        else:
            response_tollgate = "10-10"
            response_memo = f"Duration: {process_time:.2f}ms, Status: {response.status_code}"
        
        # 异步记录响应日志到数据库
        try:
            # 为大响应体创建摘要
            response_body = log_content
            if len(log_content) > 10000:
                response_body = log_content[:10000] + "... [truncated]"
            
            task = create_task(
                LogService.save_log(
                    trace_key=trace_key,
                    method_name=method_name,
                    source=source_info,
                    app_id=app_id,
                    user_uuid=user_uuid,
                    user_nickname=user_nickName,
                    entity_id=request.query_params.get("entity_id"),
                    type=tollgate_config.get("type", "response"),  # 使用装饰器中的type，默认为response
                    tollgate=response_tollgate,
                    level="info",
                    para=None,
                    header=sanitized_response_headers,
                    body=response_body,
                    memo=response_memo,
                    ip_address=client_ip
                )
            )
            register_task(task)
            
        except Exception as e:
            logger.error(f"Failed to log response to database: {str(e)}", exc_info=True)
        
        return new_response
    
    except Exception as e:
        # 异常处理
        error_message = str(e)
        logger.error(
            "Request Error: %s", error_message,
            extra={"request_id": trace_key},
            exc_info=True
        )
        
        # 计算处理时间，即使有异常
        process_time = (time.time() - start_time) * 1000
        
        # 记录错误信息到文本日志
        logger.info(
            "Response | Status=500 Duration=%.2fms",
            process_time,
            extra={
                "request_id": trace_key,
                "headers": {"error": "Exception occurred"}
            }
        )
        
        # 更新错误tollgate和备注
        if tollgate_config:
            base_gate = tollgate_config.get("base_tollgate", "1")
            # current_gate = str(int(tollgate_config.get("current_tollgate", "1")) + 2)  # 错误阶段+2
            error_tollgate = f'{base_gate}-9'
            
            title = tollgate_config.get("title", "")
            error_memo = f"[{title}] Error: {error_message}, Duration: {process_time:.2f}ms" if title else f"Error: {error_message}, Duration: {process_time:.2f}ms"
        else:
            # error_tollgate = "1-3"
            error_tollgate = f'{base_gate}-9'
            error_memo = f"Duration: {process_time:.2f}ms, Exception occurred: {error_message}"
        
        # 记录错误日志到数据库
        try:
            task = create_task(
                LogService.save_log(
                    trace_key=trace_key,
                    method_name=method_name,
                    source=source_info,
                    app_id=app_id,
                    user_uuid=user_uuid,
                    user_nickname=user_nickName,
                    entity_id=request.query_params.get("entity_id"),
                    type="error",  # 错误类型固定为error
                    tollgate=error_tollgate,
                    level="error",
                    para=None,
                    header=None,
                    body=error_message,
                    memo=error_memo,
                    ip_address=client_ip
                )
            )
            register_task(task)
            
        except Exception as log_error:
            logger.error(f"Failed to log error to database: {str(log_error)}", exc_info=True)
        
        raise

# 添加任务到注册表并设置回调以在完成时移除
def register_task(task):
    _TASK_REGISTRY.add(task)
    
    def _remove_task(_):
        _TASK_REGISTRY.discard(task)
    
    task.add_done_callback(_remove_task)

# 移除敏感头部信息
def sanitize_headers(headers):
    """移除敏感的头部信息"""
    # sensitive_keys = [
    #     'authorization', 'cookie', 'x-api-key', 'api-key', 
    #     'password', 'token', 'secret', 'credential'
    # ]
    
    # result = {}
    # for k, v in headers.items():
    #     lower_k = k.lower()
    #     if any(sensitive in lower_k for sensitive in sensitive_keys):
    #         result[k] = "******" # 隐藏敏感信息
    #     else:
    #         result[k] = v
    
    # return result
    return headers

# 关闭时等待所有日志任务完成
async def wait_for_log_tasks():
    """等待所有日志任务完成，应用退出前调用"""
    if _TASK_REGISTRY:
        logger.info(f"Waiting for {len(_TASK_REGISTRY)} log tasks to complete...")
        await asyncio.gather(*_TASK_REGISTRY, return_exceptions=True)
        logger.info("All log tasks completed.")

