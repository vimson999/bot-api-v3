# core/log_decorators.py 修正版本

import time
import functools
import inspect
from typing import Any, Callable, Optional

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx

def log_method(method_type: str = "service", tollgate: str = "20-1", level: str = "info", db_log: bool = True):
    """
    通用方法日志装饰器，支持任何类方法
    
    Args:
        method_type: 方法类型标识
        tollgate: 日志检查点标识
        level: 日志级别
        db_log: 是否记录到数据库
    """
    def decorator(func):
        # 检查是否是异步方法
        is_async = inspect.iscoroutinefunction(func)
        
        @functools.wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            start_time = time.time()
            
            # 获取方法全名
            method_name = f"{self.__class__.__module__}.{self.__class__.__name__}.{func.__name__}"
            
            # 获取trace_key
            trace_key = request_ctx.get_trace_key()
            
            # 准备参数日志
            params_log = _format_params(args, kwargs)
            
            # 记录开始日志
            logger.debug(f"方法调用开始: {method_name}", extra={"request_id": trace_key, "params": params_log})
            
            # 如果需要记录到数据库
            if db_log:
                logger.db_logging_context(
                    method_name=method_name,
                    type=method_type,
                    tollgate=tollgate
                )
            
            try:
                # 执行方法
                result = await func(self, *args, **kwargs)
                
                # 计算执行时间
                duration = time.time() - start_time
                
                # 记录成功日志
                logger.debug(
                    f"方法调用成功: {method_name}, 耗时: {duration:.2f}s",
                    extra={"request_id": trace_key, "duration": duration}
                )
                
                return result
                
            except Exception as e:
                # 计算执行时间
                duration = time.time() - start_time
                
                # 记录错误日志
                logger.error(
                    f"方法调用失败: {method_name}, 错误: {str(e)}, 耗时: {duration:.2f}s",
                    extra={"request_id": trace_key, "duration": duration},
                    exc_info=True
                )
                
                # 重新抛出异常
                raise
        
        @functools.wraps(func)
        def sync_wrapper(self, *args, **kwargs):
            # 同步方法实现
            start_time = time.time()
            
            # 获取方法全名
            method_name = f"{self.__class__.__module__}.{self.__class__.__name__}.{func.__name__}"
            
            # 获取trace_key
            trace_key = request_ctx.get_trace_key()
            
            # 准备参数日志
            params_log = _format_params(args, kwargs)
            
            # 记录开始日志
            logger.debug(f"方法调用开始: {method_name}", extra={"request_id": trace_key, "params": params_log})
            
            try:
                # 执行方法
                result = func(self, *args, **kwargs)
                
                # 计算执行时间
                duration = time.time() - start_time
                
                # 记录成功日志
                logger.debug(
                    f"方法调用成功: {method_name}, 耗时: {duration:.2f}s",
                    extra={"request_id": trace_key, "duration": duration}
                )
                
                return result
                
            except Exception as e:
                # 计算执行时间
                duration = time.time() - start_time
                
                # 记录错误日志
                logger.error(
                    f"方法调用失败: {method_name}, 错误: {str(e)}, 耗时: {duration:.2f}s",
                    extra={"request_id": trace_key, "duration": duration},
                    exc_info=True
                )
                
                # 重新抛出异常
                raise
        
        # 根据方法类型返回相应的包装器
        if is_async:
            return async_wrapper
        return sync_wrapper
    
    return decorator

def _format_params(args, kwargs):
    """格式化方法参数"""
    # 简单实现参数格式化
    params = {}
    
    # 添加位置参数
    if args and len(args) > 0:
        params['args'] = [str(arg)[:100] for arg in args]
        
    # 添加关键字参数，过滤掉敏感信息
    if kwargs and len(kwargs) > 0:
        params['kwargs'] = {}
        for key, value in kwargs.items():
            # 过滤敏感字段
            if any(sensitive in key.lower() for sensitive in ['password', 'token', 'secret', 'key']):
                params['kwargs'][key] = "******"
            else:
                params['kwargs'][key] = str(value)[:100]
    
    return params