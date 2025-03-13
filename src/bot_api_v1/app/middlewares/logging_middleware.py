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
from bot_api_v1.app.tasks.base import register_task, TASK_TYPE_LOG
from bot_api_v1.app.core.decorators import get_tollgate_config
from bot_api_v1.app.core.context import request_ctx
from datetime import datetime


async def init_request_context(request: Request, trace_key: str):
    """初始化请求上下文，提取并处理请求头信息"""
    # 安全获取请求头
    try:
        headers_dict = dict(request.headers.items())
        sanitized_headers = {k: v for k, v in headers_dict.items() if not k.lower().startswith('authorization')}
    except Exception:
        headers_dict = {}
        sanitized_headers = {"info": "Unable to parse headers"}
    
    # 尝试获取客户端IP
    client_ip = request.client.host if request.client else None
    
    # 提取请求路径作为方法名
    method_name = f"{request.method}:{request.url.path}"
    
    # 提取用户信息
    app_id = headers_dict.get('x-app-id', headers_dict.get('X-App-Id'))
    source_info = headers_dict.get('x-source', headers_dict.get('X-Source', 'api'))
    user_uuid = headers_dict.get('x-user-uuid', headers_dict.get('X-User-Uuid'))
    user_nickname = headers_dict.get('x-user-nickname', headers_dict.get('X-User-Nickname'))
    
    # 解决用户昵称的中文乱码问题
    try:
        if isinstance(user_nickname, bytes):
            user_nickname = user_nickname.decode('utf-8')
        elif user_nickname and isinstance(user_nickname, str):
            # 尝试解决乱码
            user_nickname = user_nickname.encode('latin1').decode('utf-8')
    except Exception:
        user_nickname = '-'
    
    # 获取tollgate相关的信息
    tollgate_config = get_tollgate_config_for_route(request)
    base_tollgate = "10"  # 默认值
    current_tollgate = "1"  # 默认值
    
    if tollgate_config:
        base_tollgate = tollgate_config.get("base_tollgate", "10")
        current_tollgate = tollgate_config.get("current_tollgate", "1")
    
    # 构建上下文数据
    context_data = {
        'trace_key': trace_key,
        'method_name': method_name,
        'source': source_info,
        'app_id': app_id,
        'user_id': user_uuid,
        'user_name': user_nickname,
        'ip_address': client_ip,
        'base_tollgate': base_tollgate,
        'current_tollgate': current_tollgate,
        'request_time': datetime.now().isoformat(),
    }
    
    # 设置上下文
    request_ctx.set_context(context_data)
    
    # 记录调试信息
    logger.info(
        f"Request | Method={request.method} Path={request.url.path}",
        extra={
            "request_id": trace_key,
            "headers": sanitized_headers
        }
    )
    
    return context_data, sanitized_headers


def get_tollgate_config_for_route(request: Request):
    """获取路由的tollgate配置"""
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
            
            # 如果找到了配置，立即更新请求上下文
            # if tollgate_config:
            #     context = request_ctx.get_context()
            #     if 'base_tollgate' in tollgate_config:
            #         context['base_tollgate'] = tollgate_config['base_tollgate']
            #     if 'current_tollgate' in tollgate_config:
            #         context['current_tollgate'] = tollgate_config['current_tollgate']
            #     if 'plat' in tollgate_config and tollgate_config['plat']:
            #         context['source'] = tollgate_config['plat']
            #     request_ctx.set_context(context)
    except Exception as e:
        logger.warning(f"Unable to extract route handler: {str(e)}")
    
    return tollgate_config


async def extract_request_body(request: Request):
    """提取并处理请求体"""
    request_body = None
    
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
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
            
        except Exception as e:
            logger.error(f"Error extracting request body: {str(e)}")
            request_body = {"error": "Failed to extract body"}
    
    return request_body


async def log_request(request: Request, trace_key: str, context_data: dict, 
                     request_body: dict, sanitized_headers: dict, tollgate_config: dict):
    """记录请求日志到数据库"""
    try:
        # 获取上下文数据
        source_info = context_data.get('source')
        app_id = context_data.get('app_id')
        user_uuid = context_data.get('user_id')
        user_nickname = context_data.get('user_name')
        method_name = context_data.get('method_name')
        client_ip = context_data.get('ip_address')
        
        # 获取请求tollgate
        base_tollgate = context_data.get('base_tollgate')
        current_tollgate = context_data.get('current_tollgate')
        
        if base_tollgate and current_tollgate:
            # 使用上下文中的tollgate信息
            log_tollgate = f"{base_tollgate}-{current_tollgate}"
        elif tollgate_config:
            # 处理tollgate相关信息 (兼容旧方式)
            if 'plat' in tollgate_config and tollgate_config['plat'] and not source_info:
                source_info = tollgate_config['plat']
            
            # 构造tollgate标识
            if 'base_tollgate' in tollgate_config and 'current_tollgate' in tollgate_config:
                log_tollgate = f"{tollgate_config['base_tollgate']}-{tollgate_config['current_tollgate']}"
            else:
                log_tollgate = "10-1"
        else:
            log_tollgate = "10-1"
        
        # 构造备注信息
        if tollgate_config and 'title' in tollgate_config and tollgate_config['title']:
            title_prefix = f"[{tollgate_config['title']}] "
            log_memo = title_prefix + "Request"
        else:
            log_memo = "Request"
        
        # 安全获取请求参数
        query_params = dict(request.query_params)
        
        # 使用全局任务管理系统注册日志任务
        # 名称包含请求路径以便于追踪
        task_name = f"log_request:{request.url.path}"
        
        # 注册异步任务，不等待其完成
        register_task(
            name=task_name,
            coro=LogService.save_log(
                trace_key=trace_key,
                method_name=method_name,
                source=source_info,
                app_id=app_id,
                user_uuid=user_uuid,
                user_nickname=user_nickname,
                entity_id=request.query_params.get("entity_id"),
                type=tollgate_config.get("type", "request") if tollgate_config else "request",
                tollgate=log_tollgate,
                level="info",
                para=query_params,
                header=sanitized_headers,
                body=request_body,
                memo=log_memo,
                ip_address=client_ip
            ),
            timeout=60,  # 设置日志超时时间为60秒
            task_type=TASK_TYPE_LOG
        )
        
    except Exception as e:
        logger.error(f"Failed to log request to database: {str(e)}", exc_info=True)


async def process_response_body(response: Response):
    """处理响应体"""
    # 克隆响应体
    resp_body = []
    async for chunk in response.body_iterator:
        resp_body.append(chunk)
    content = b''.join(resp_body)
    
    # 尝试解码响应内容
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
        sanitized_response_headers = {k: v for k, v in response_headers.items() 
                                     if not k.lower().startswith('authorization')}
    except Exception:
        sanitized_response_headers = {"info": "Unable to parse response headers"}
    
    # 重建响应
    new_response = Response(
        content=content,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type
    )
    
    return new_response, log_content, sanitized_response_headers


async def log_response(response: Response, request: Request, trace_key: str, 
                      start_time: float, context_data: dict, tollgate_config: dict,
                      log_content: str, sanitized_response_headers: dict):
    """记录响应日志到数据库和文本日志"""
    # 计算处理时间
    process_time = (time.time() - start_time) * 1000
    
    # 获取上下文数据
    source_info = context_data.get('source')
    app_id = context_data.get('app_id')
    user_uuid = context_data.get('user_id')
    user_nickname = context_data.get('user_name')
    method_name = context_data.get('method_name')
    client_ip = context_data.get('ip_address')
    

    # 更新响应tollgate - 使用base-base表示流程结束
    base_tollgate = context_data.get('base_tollgate')
    
    if base_tollgate:
        # 使用base-base表示完成
        response_tollgate = f'{base_tollgate}-{base_tollgate}'
    elif tollgate_config:
        # 兼容旧的tollgate配置方式
        base_gate = tollgate_config.get("base_tollgate", "10")
        response_tollgate = f'{base_gate}-{base_gate}'  # 使用base-base表示完成
    else:
        response_tollgate = "10-10"  # 默认完成状态

    # 记录详细响应日志到文本
    logger.debug(
        "Response Content | Status=%d Size=%d\n%s",
        response.status_code,
        len(log_content),
        log_content[:500],  # 只记录前500个字符
        extra={
            "request_id": trace_key,
            "headers": sanitized_response_headers,
            "tollgate": response_tollgate
        }
    )
    
    # 记录响应信息到文本日志
    logger.info(
        "Response | Status=%d Duration=%.2fms" % (response.status_code, process_time),
        extra={
            "request_id": trace_key,
            "headers": sanitized_response_headers,
            "tollgate": response_tollgate
        }
    )
    
    # 构造备注信息
    title = tollgate_config.get("title", "") if tollgate_config else ""
    response_memo = f"[{title}] Duration: {process_time:.2f}ms, Status: {response.status_code}" if title else f"Duration: {process_time:.2f}ms, Status: {response.status_code}"
    
    # 异步记录响应日志到数据库
    try:
        # 为大响应体创建摘要
        response_body = log_content
        if len(log_content) > 10000:
            response_body = log_content[:10000] + "... [truncated]"
        
        # 使用全局任务管理系统注册日志任务
        task_name = f"log_response:{request.url.path}"
        
        register_task(
            name=task_name,
            coro=LogService.save_log(
                trace_key=trace_key,
                method_name=method_name,
                source=source_info,
                app_id=app_id,
                user_uuid=user_uuid,
                user_nickname=user_nickname,
                entity_id=request.query_params.get("entity_id"),
                type=tollgate_config.get("type", "response") if tollgate_config else "response",
                tollgate=response_tollgate,
                level="info",
                para=None,
                header=sanitized_response_headers,
                body=response_body,
                memo=response_memo,
                ip_address=client_ip
            ),
            timeout=60,  # 设置日志超时时间为60秒
            task_type=TASK_TYPE_LOG
        )
        
    except Exception as e:
        logger.error(f"Failed to log response to database: {str(e)}", exc_info=True)


async def log_error(e: Exception, request: Request, trace_key: str, 
                   start_time: float, context_data: dict, tollgate_config: dict):
    """记录错误日志到数据库和文本日志"""
    # 异常处理
    error_message = str(e)
    logger.error(
        "Request Error: %s", error_message,
        extra={"request_id": trace_key},
        exc_info=True
    )
    
    # 计算处理时间，即使有异常
    process_time = (time.time() - start_time) * 1000
    
    # 获取上下文数据
    source_info = context_data.get('source')
    app_id = context_data.get('app_id')
    user_uuid = context_data.get('user_id')
    user_nickname = context_data.get('user_name')
    method_name = context_data.get('method_name')
    client_ip = context_data.get('ip_address')
    
    # 记录错误信息到文本日志
    logger.info(
        "Response | Status=500 Duration=%.2fms" % process_time,
        extra={
            "request_id": trace_key,
            "headers": {"error": "Exception occurred"}
        }
    )
    
    # 更新错误tollgate
    base_tollgate = context_data.get('base_tollgate')
    
    if base_tollgate:
        # 错误情况使用固定的tollgate结尾：9
        error_tollgate = f'{base_tollgate}-9'
    elif tollgate_config:
        # 兼容旧的tollgate配置方式
        base_gate = tollgate_config.get("base_tollgate", "10")
        error_tollgate = f'{base_gate}-9'
    else:
        base_gate = "10"
        error_tollgate = f'{base_gate}-9'
    
    # 构造备注信息
    title = tollgate_config.get("title", "") if tollgate_config else ""
    error_memo = f"[{title}] Error: {error_message}, Duration: {process_time:.2f}ms" if title else f"Error: {error_message}, Duration: {process_time:.2f}ms"
    
    # 记录错误日志到数据库
    try:
        # 使用全局任务管理系统注册日志任务
        task_name = f"log_error:{request.url.path}"
        
        register_task(
            name=task_name,
            coro=LogService.save_log(
                trace_key=trace_key,
                method_name=method_name,
                source=source_info,
                app_id=app_id,
                user_uuid=user_uuid,
                user_nickname=user_nickname,
                entity_id=request.query_params.get("entity_id"),
                type="error",  # 错误类型固定为error
                tollgate=error_tollgate,
                level="error",
                para=None,
                header=None,
                body=error_message,
                memo=error_memo,
                ip_address=client_ip
            ),
            timeout=60,  # 设置日志超时时间为60秒
            task_type=TASK_TYPE_LOG
        )
        
    except Exception as log_error:
        logger.error(f"Failed to log error to database: {str(log_error)}", exc_info=True)


async def log_middleware(request: Request, call_next):
    """主中间件函数，协调各模块的执行"""
    # 生成唯一追踪ID
    trace_key = str(uuid.uuid4())
    start_time = time.time()

    # 1. 初始化上下文
    context_data, sanitized_headers = await init_request_context(request, trace_key)
    
    # 2. 获取tollgate配置
    tollgate_config = get_tollgate_config_for_route(request)
    
    # 3. 提取请求体
    request_body = await extract_request_body(request)
    
    # 4. 记录请求日志
    await log_request(request, trace_key, context_data, request_body, 
                     sanitized_headers, tollgate_config)

    # 5. 处理请求
    try:
        response = await call_next(request)
        
        # 6. 处理响应体
        new_response, log_content, sanitized_response_headers = await process_response_body(response)
        
        # 7. 记录响应日志
        await log_response(response, request, trace_key, start_time, context_data, 
                          tollgate_config, log_content, sanitized_response_headers)
        
        return new_response
    
    except Exception as e:
        # 8. 记录错误日志
        await log_error(e, request, trace_key, start_time, context_data, tollgate_config)
        raise


# 关闭时等待所有日志任务完成的函数已迁移到 tasks/base.py 中的 wait_for_log_tasks
async def wait_for_log_tasks(timeout: int = 5):
    """等待所有日志任务完成（兼容旧版本API）
    
    Args:
        timeout: 最长等待时间（秒）
    """
    from bot_api_v1.app.tasks.base import wait_for_log_tasks as base_wait_for_log_tasks
    await base_wait_for_log_tasks(timeout=timeout)