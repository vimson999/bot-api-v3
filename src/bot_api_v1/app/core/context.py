"""
请求上下文管理模块

提供请求上下文的存储和获取，用于在不同模块间传递请求信息，
特别是在中间件和服务层之间传递日志追踪标识(trace_key)和积分信息等。

使用了线程局部存储(contextvars)，确保在异步环境中正确工作。
"""
from contextvars import ContextVar
from typing import Any, Dict, Optional, Union
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
    def get_root_trace_key() -> str:
        """获取当前请求的根追踪标识

        如果不存在，则自动生成一个新的
        """
        ctx = _request_ctx_var.get()
        root_trace_key = ctx.get ('root_trace_key')
        if not root_trace_key:
            root_trace_key = ctx.get('trace_key')

        return root_trace_key
    
    @staticmethod
    def set_root_trace_key(root_trace_key: str) -> None:
        """设置当前请求的根追踪标识"""
        ctx = _request_ctx_var.get()
        ctx['root_trace_key'] = root_trace_key
        _request_ctx_var.set(ctx)

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
        
    @staticmethod
    def get_app_id() -> str:
        """获取应用ID"""
        return _request_ctx_var.get().get("app_id", "-")
    
    @staticmethod
    def get_user_id() -> str:
        """获取用户ID"""
        return _request_ctx_var.get().get("user_id", "-")
    
    @staticmethod
    def get_user_name() -> str:
        """获取用户名称"""
        return _request_ctx_var.get().get("user_name", "-")
    
    @staticmethod
    def get_base_tollgate() -> str:
        """获取基础检查点"""
        return _request_ctx_var.get().get("base_tollgate", "-")
    
    @staticmethod
    def get_current_tollgate() -> str:
        """获取当前检查点"""
        return _request_ctx_var.get().get("current_tollgate", "-")
    
    @staticmethod
    def get_whole_tollgate() -> str:
        """获取完整检查点标识"""
        return f'{_request_ctx_var.get().get("base_tollgate", "-")}-{_request_ctx_var.get().get("current_tollgate", "-")}'
    



    @staticmethod
    def get_cappa_user_id() -> str:
        """获取当前检查点"""
        return _request_ctx_var.get().get("cappa_user_id", "-")

    @staticmethod
    def set_cappa_user_id(cappa_user_id: str) -> None:
        ctx = _request_ctx_var.get()
        ctx['cappa_user_id'] = cappa_user_id
        
        _request_ctx_var.set(ctx)


    # 新增积分相关方法
    @staticmethod
    def set_points_info(account_id: str, available_points: int, user_id: str = None) -> None:
        """设置当前请求的用户积分信息
        
        Args:
            account_id: 积分账户ID
            available_points: 可用积分数量
            user_id: 用户ID（可选）
        """
        ctx = _request_ctx_var.get()
        ctx['points_account_id'] = account_id
        ctx['available_points'] = available_points
        if user_id:
            ctx['points_user_id'] = user_id
        _request_ctx_var.set(ctx)
    
    @staticmethod
    def set_consumed_points(points: int, api_name: str = None) -> None:
        """设置当前请求消耗的积分
        
        Args:
            points: 消耗的积分数量
            api_name: API名称，用于记录积分消费来源
        """
        ctx = _request_ctx_var.get()
        ctx['consumed_points'] = points
        if api_name:
            ctx['api_name'] = api_name
        _request_ctx_var.set(ctx)
    


    @staticmethod
    def get_points_info() -> Dict[str, Any]:
        """获取当前请求相关的积分信息
        
        Returns:
            Dict: 包含账户ID、可用积分和已消耗积分的字典
        """
        ctx = _request_ctx_var.get()
        return {
            'account_id': ctx.get('points_account_id'),
            'user_id': ctx.get('points_user_id'),
            'available_points': ctx.get('available_points', 0),
            'consumed_points': ctx.get('consumed_points', 0),
            'api_name': ctx.get('api_name', '未知API')
        }

# 默认导出的请求上下文实例
request_ctx = RequestContext()