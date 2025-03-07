"""
服务层日志装饰器模块

提供用于服务层方法的日志装饰器，自动记录方法的输入输出和执行时间，
并保持与请求上下文的链路追踪关系。记录日志同时到文本日志和数据库。
"""
import time
import functools
import inspect
import asyncio
from typing import Any, Callable, Optional, Dict, Type, TypeVar, cast
import traceback
import json

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.services.log_service import LogService

F = TypeVar('F', bound=Callable[..., Any])


def log_service_call(
    method_type: str = "service", 
    tollgate: str = "20-1",
    level: str = "info"
) -> Callable[[F], F]:
    """
    记录服务调用的装饰器
    
    自动记录服务方法的输入参数、返回值、执行时间，同时保持与请求上下文的链路关系。
    同时将日志记录到文本日志和数据库。
    
    Args:
        method_type: 方法类型，例如 "service", "repository", "script" 等
        tollgate: 日志检查点标识
        level: 日志级别，可选值: "debug", "info", "warning", "error", "critical"
    
    Returns:
        装饰后的函数
    """
    def decorator(func: F) -> F:
        # 是否是异步函数
        is_async = inspect.iscoroutinefunction(func)
        
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            
            # 获取函数签名
            sig = inspect.signature(func)
            # 函数参数绑定
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # 忽略self参数
            params = dict(bound_args.arguments)
            if 'self' in params:
                params.pop('self')
            
            # 格式化参数
            params_str = _format_params(params)
            
            # 获取上下文信息
            trace_key = request_ctx.get_trace_key()
            
            # 获取函数限定名
            qualified_name = f"{func.__module__}.{func.__qualname__}"
            
            # 记录开始日志
            logger.debug(
                f"服务调用开始: {qualified_name}",
                extra={
                    "request_id": trace_key,
                    "params": params_str
                }
            )
            
            try:
                # 异步调用函数
                result = await func(*args, **kwargs)
                
                # 计算执行时间
                end_time = time.time()
                duration = end_time - start_time
                
                # 格式化结果
                result_str = _format_result(result)
                
                # 记录成功日志
                log_message = f"服务调用成功: {qualified_name}, 耗时: {duration:.2f}s"
                logger.debug(
                    log_message,
                    extra={
                        "request_id": trace_key,
                        "duration": duration,
                        "result": result_str
                    }
                )
                
                # 异步记录到数据库
                await _log_to_database(
                    trace_key=trace_key,
                    method_name=qualified_name,
                    tollgate=tollgate,
                    level=level,
                    method_type=method_type,
                    params=params,
                    result=result,
                    duration=duration,
                    success=True
                )
                
                return result
                
            except Exception as e:
                # 计算执行时间
                end_time = time.time()
                duration = end_time - start_time
                
                # 获取异常信息
                error_msg = str(e)
                error_traceback = traceback.format_exc()
                
                # 记录错误日志
                log_message = f"服务调用失败: {qualified_name}, 错误: {error_msg}, 耗时: {duration:.2f}s"
                logger.error(
                    log_message,
                    extra={
                        "request_id": trace_key,
                        "error": error_msg,
                        "traceback": error_traceback,
                        "duration": duration
                    }
                )
                
                # 异步记录到数据库
                await _log_to_database(
                    trace_key=trace_key,
                    method_name=qualified_name,
                    tollgate=f"{tollgate.split('-')[0]}-9",  # 错误tollgate
                    level="error",
                    method_type=method_type,
                    params=params,
                    error=error_msg,
                    duration=duration,
                    success=False
                )
                
                # 重新抛出异常
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            
            # 获取函数签名
            sig = inspect.signature(func)
            # 函数参数绑定
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # 忽略self参数
            params = dict(bound_args.arguments)
            if 'self' in params:
                params.pop('self')
            
            # 格式化参数
            params_str = _format_params(params)
            
            # 获取上下文信息
            trace_key = request_ctx.get_trace_key()
            
            # 获取函数限定名
            qualified_name = f"{func.__module__}.{func.__qualname__}"
            
            # 记录开始日志
            logger.debug(
                f"服务调用开始: {qualified_name}",
                extra={
                    "request_id": trace_key,
                    "params": params_str
                }
            )
            
            try:
                # 调用函数
                result = func(*args, **kwargs)
                
                # 计算执行时间
                end_time = time.time()
                duration = end_time - start_time
                
                # 格式化结果
                result_str = _format_result(result)
                
                # 记录成功日志
                log_message = f"服务调用成功: {qualified_name}, 耗时: {duration:.2f}s"
                logger.debug(
                    log_message,
                    extra={
                        "request_id": trace_key,
                        "duration": duration,
                        "result": result_str
                    }
                )
                
                # 创建异步任务记录到数据库，但不等待
                asyncio.create_task(
                    _log_to_database(
                        trace_key=trace_key,
                        method_name=qualified_name,
                        tollgate=tollgate,
                        level=level,
                        method_type=method_type,
                        params=params,
                        result=result,
                        duration=duration,
                        success=True
                    )
                )
                
                return result
                
            except Exception as e:
                # 计算执行时间
                end_time = time.time()
                duration = end_time - start_time
                
                # 获取异常信息
                error_msg = str(e)
                error_traceback = traceback.format_exc()
                
                # 记录错误日志
                log_message = f"服务调用失败: {qualified_name}, 错误: {error_msg}, 耗时: {duration:.2f}s"
                logger.error(
                    log_message,
                    extra={
                        "request_id": trace_key,
                        "error": error_msg,
                        "traceback": error_traceback,
                        "duration": duration
                    }
                )
                
                # 创建异步任务记录到数据库，但不等待
                asyncio.create_task(
                    _log_to_database(
                        trace_key=trace_key,
                        method_name=qualified_name,
                        tollgate=f"{tollgate.split('-')[0]}-9",  # 错误tollgate
                        level="error",
                        method_type=method_type,
                        params=params,
                        error=error_msg,
                        duration=duration,
                        success=False
                    )
                )
                
                # 重新抛出异常
                raise
        
        # 根据原函数类型返回对应的包装器
        if is_async:
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)
    
    return decorator


def _format_params(params: Dict[str, Any]) -> str:
    """格式化参数，过滤敏感信息"""
    try:
        # 深拷贝避免修改原数据
        safe_params = params.copy()
        
        # 过滤敏感字段
        sensitive_keys = ['password', 'token', 'secret', 'key']
        for key in safe_params:
            if any(s in key.lower() for s in sensitive_keys):
                safe_params[key] = "******"
        
        # 转为JSON字符串，限制长度
        params_json = json.dumps(safe_params, default=str)
        if len(params_json) > 5000:  # 限制参数日志长度
            params_json = params_json[:5000] + "... [truncated]"
        
        return params_json
    except Exception:
        return str(params)


def _format_result(result: Any) -> str:
    """格式化返回结果，处理长结果"""
    try:
        # 转为JSON字符串，限制长度
        result_json = json.dumps(result, default=str)
        if len(result_json) > 1000:  # 限制结果日志长度
            result_json = result_json[:1000] + "... [truncated]"
        
        return result_json
    except Exception:
        return str(result)


async def _log_to_database(
    trace_key: str,
    method_name: str,
    tollgate: str,
    level: str,
    method_type: str,
    params: Dict[str, Any],
    duration: float,
    success: bool,
    result: Any = None,
    error: Optional[str] = None
) -> None:
    """记录服务调用日志到数据库"""
    try:
        # 构造日志数据
        body_dict = {
            "success": success,
            "duration_ms": round(duration * 1000, 2)
        }
        
        if success and result is not None:
            # 成功情况下记录结果摘要
            if isinstance(result, dict):
                body_dict["result_summary"] = {k: "..." for k in result.keys()}
            elif isinstance(result, list):
                body_dict["result_summary"] = f"List with {len(result)} items"
            else:
                body_dict["result_summary"] = str(result)[:100]
        
        if not success and error:
            body_dict["error"] = error
        
        # 序列化body为JSON字符串
        body = json.dumps(body_dict)
        
        # 构造备注信息
        memo = f"{method_type.capitalize()} call: {method_name}"
        if success:
            memo += f", duration: {duration:.2f}s"
        else:
            memo += f", failed: {error}"
        
        # 从上下文获取其他信息
        ctx = request_ctx.get_context()
        source = ctx.get('source', 'api')
        app_id = ctx.get('app_id')
        user_uuid = ctx.get('user_uuid')
        user_nickname = ctx.get('user_nickname')
        ip_address = ctx.get('ip_address')
        
        # 调用LogService记录日志到数据库
        await LogService.save_log(
            trace_key=trace_key,
            method_name=method_name,
            source=source or "service",
            app_id=app_id,
            user_uuid=user_uuid,
            user_nickname=user_nickname,
            entity_id=None,  # 服务调用通常没有entity_id
            type=method_type,
            tollgate=tollgate,
            level=level,
            para=params,
            header=None,  # 服务调用不需要header
            body=body,
            memo=memo,
            ip_address=ip_address
        )
        
    except Exception as e:
        # 记录服务日志失败，使用文本日志记录
        logger.error(f"记录服务调用日志到数据库失败: {str(e)}", exc_info=True)