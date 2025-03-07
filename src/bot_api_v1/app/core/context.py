"""
请求上下文管理模块

提供请求上下文的存储和获取，用于在不同模块间传递请求信息，
特别是在中间件和服务层之间传递日志追踪标识(trace_key)等信息。

使用了线程局部存储(contextvars)，确保在异步环境中正确工作。
"""
from contextvars import ContextVar
from typing import Any, Dict, Optional
import uuid
import json
from datetime import datetime

# 上下文变量，使用contextvars确保在异步环境正常工作
_request_ctx_var: ContextVar[Dict[str, Any]] = ContextVar('request_context', default={})


class RequestContext:
    """请求上下文管理类"""
    
    @staticmethod
    def get_context() -> Dict[str, Any]:
        """获取当前请求的上下文数据"""
        return _request_ctx_var.get()
    
    @staticmethod
    def set_context(ctx: Dict[str, Any]) -> None:
        """设置当前请求的上下文数据"""
        _request_ctx_var.set(ctx)
    
    @staticmethod
    def update_context(**kwargs) -> None:
        """更新当前请求的上下文数据"""
        ctx = _request_ctx_var.get()
        ctx.update(kwargs)
        _request_ctx_var.set(ctx)
    
    @staticmethod
    def clear_context() -> None:
        """清除当前请求的上下文数据"""
        _request_ctx_var.set({})
    
    @staticmethod
    def get_trace_key() -> str:
        """获取当前请求的追踪标识

        如果不存在，则自动生成一个新的
        """
        ctx = _request_ctx_var.get()
        if 'trace_key' not in ctx:
            ctx['trace_key'] = str(uuid.uuid4())
            _request_ctx_var.set(ctx)
        return ctx['trace_key']
    
    @staticmethod
    def get_method_name() -> Optional[str]:
        """获取当前请求的方法名"""
        return _request_ctx_var.get().get('method_name')
    
    @staticmethod
    def get_source() -> str:
        """获取当前请求的来源"""
        return _request_ctx_var.get().get('source', 'api')
    
    @staticmethod
    def get_all_context() -> str:
        """获取所有上下文数据，格式化为JSON字符串"""
        ctx = _request_ctx_var.get()
        return json.dumps(ctx, default=str)
    
    @staticmethod
    def get_request_id() -> str:
        """获取请求ID，与trace_key同义"""
        return RequestContext.get_trace_key()


# 默认导出的请求上下文实例
request_ctx = RequestContext()