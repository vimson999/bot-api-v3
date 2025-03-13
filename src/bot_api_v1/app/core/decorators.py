from functools import wraps
import inspect
from typing import Optional, Dict, Any, Callable, Union
from fastapi import Request
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.logger import logger

class TollgateConfig:
    """
    路由函数的Tollgate配置装饰器
    用于标记API端点的测量点信息，便于日志跟踪和请求链路分析
    """
    def __init__(
        self,
        title: str,
        type: str,
        base_tollgate: str = "1",
        current_tollgate: str = "1",
        plat: str = "api"
    ):
        """
        初始化TollgateConfig装饰器
        
        Args:
            title: 操作标题，用于明确标识API操作类型
            type: 操作类型，例如 "query", "update", "create" 等
            base_tollgate: 基础tollgate标识，表示功能模块的基础编号
            current_tollgate: 当前tollgate标识，表示处理阶段的编号
            plat: 平台标识，表示请求来源，例如 "web", "mobile", "api" 等
        """
        self.title = title
        self.type = type
        self.base_tollgate = base_tollgate
        self.current_tollgate = current_tollgate
        self.plat = plat
    
    def __call__(self, func):
        # 将配置信息存储到函数属性中
        func._tollgate_config = {
            "title": self.title,
            "type": self.type,
            "base_tollgate": self.base_tollgate,
            "current_tollgate": self.current_tollgate,
            "plat": self.plat
        }
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 在执行函数前更新请求上下文
            context = request_ctx.get_context()
            original_source = context.get('source')  # 保存原始source值
            context['base_tollgate'] = self.base_tollgate
            context['current_tollgate'] = self.current_tollgate
            if self.plat and not original_source:  # 只在没有原始source值时使用plat
                context['source'] = self.plat
            request_ctx.set_context(context)
            
            # 执行原函数
            return await func(*args, **kwargs)
        
        # 将配置信息复制到wrapper函数
        wrapper._tollgate_config = func._tollgate_config
        return wrapper


def get_tollgate_config(func: Callable) -> Dict[str, Any]:
    """
    从函数中获取Tollgate配置信息
    
    Args:
        func: 函数对象
    
    Returns:
        包含Tollgate配置的字典
    """
    return getattr(func, "_tollgate_config", {})


def get_request_from_args(*args) -> Optional[Request]:
    """
    从函数参数中提取Request对象
    
    Args:
        *args: 函数参数
        
    Returns:
        Request对象或None
    """
    for arg in args:
        if isinstance(arg, Request):
            return arg
    return None