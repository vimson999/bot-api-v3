from functools import wraps
import inspect
from typing import Optional, Dict, Any, Callable
from fastapi import Request

class TollgateConfig:
    """
    路由函数的Tollgate配置装饰器
    用于标记API端点的测量点信息，便于日志跟踪
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
            title: 操作标题
            type: 操作类型
            base_tollgate: 基础tollgate标识
            current_tollgate: 当前tollgate标识
            plat: 平台标识
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
