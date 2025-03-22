"""
请求计数中间件，用于追踪请求统计信息
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time

class RequestCounterMiddleware(BaseHTTPMiddleware):
    """
    请求计数中间件
    
    追踪和统计API请求数量，按端点、方法和状态码分类
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        处理请求并计数
        
        Args:
            request: 请求对象
            call_next: 下一个中间件或路由处理函数
            
        Returns:
            响应对象
        """
        # 提取请求信息
        path = request.url.path
        method = request.method
        
        # 对 /metrics 和 /health 路径特殊处理，避免它们影响统计
        if path in ["/metrics", "/api/health", "/favicon.ico"]:
            return await call_next(request)
        
        # 记录开始时间
        start_time = time.time()
        
        # 初始化计数器，如果应用状态中不存在
        if not hasattr(request.app.state, "request_counts"):
            request.app.state.request_counts = {
                "total": 0,
                "success": 0,
                "error": 0,
                "by_endpoint": {},
                "by_method": {}
            }
            
        # 确保路径和方法计数器存在
        counts = request.app.state.request_counts
        
        if path not in counts["by_endpoint"]:
            counts["by_endpoint"][path] = {
                "total": 0, 
                "success": 0, 
                "error": 0,
                "avg_time_ms": 0
            }
            
        if method not in counts["by_method"]:
            counts["by_method"][method] = {
                "total": 0, 
                "success": 0, 
                "error": 0
            }
            
        try:
            # 处理请求
            response = await call_next(request)
            
            # 计算请求处理时间
            duration_ms = (time.time() - start_time) * 1000
            
            # 更新计数器
            counts["total"] += 1
            counts["by_endpoint"][path]["total"] += 1
            counts["by_method"][method]["total"] += 1
            
            # 根据状态码更新成功/错误计数
            if response.status_code < 400:
                counts["success"] += 1
                counts["by_endpoint"][path]["success"] += 1
                counts["by_method"][method]["success"] += 1
            else:
                counts["error"] += 1
                counts["by_endpoint"][path]["error"] += 1
                counts["by_method"][method]["error"] += 1
            
            # 更新平均响应时间（使用加权平均）
            old_avg = counts["by_endpoint"][path]["avg_time_ms"]
            old_count = counts["by_endpoint"][path]["total"] - 1
            
            if old_count > 0:
                new_avg = (old_avg * old_count + duration_ms) / counts["by_endpoint"][path]["total"]
                counts["by_endpoint"][path]["avg_time_ms"] = round(new_avg, 2)
            else:
                counts["by_endpoint"][path]["avg_time_ms"] = round(duration_ms, 2)
            
            return response
            
        except Exception as e:
            # 更新错误计数
            counts["total"] += 1
            counts["error"] += 1
            counts["by_endpoint"][path]["total"] += 1
            counts["by_endpoint"][path]["error"] += 1
            counts["by_method"][method]["total"] += 1
            counts["by_method"][method]["error"] += 1
            
            # 重新抛出异常
            raise

def add_request_counter(app):
    """
    向FastAPI应用添加请求计数中间件
    
    Args:
        app: FastAPI应用实例
    """
    app.add_middleware(RequestCounterMiddleware)