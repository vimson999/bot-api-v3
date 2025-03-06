import time
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from bot_api_v1.app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.rate_limit = settings.RATE_LIMIT_PER_MINUTE
        self.window = 60  # 1分钟窗口
        self.clients = {}
        
    async def dispatch(self, request: Request, call_next):
        # 获取客户端标识符 - 可以是IP地址或授权令牌
        client_id = request.client.host
        current_time = time.time()
        
        # 获取客户端的请求历史
        if client_id not in self.clients:
            self.clients[client_id] = []
        
        # 清理过期的请求记录
        self.clients[client_id] = [
            timestamp for timestamp in self.clients[client_id]
            if current_time - timestamp < self.window
        ]
        
        # 检查请求数量是否超过限制
        if len(self.clients[client_id]) >= self.rate_limit:
            logger.warning(
                f"Rate limit exceeded for client {client_id}",
                extra={"request_id": getattr(request.state, "request_id", "unknown")}
            )
            
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "code": "rate_limit_exceeded",
                    "message": "Too many requests",
                    "details": {"retry_after": self.window},
                },
            )
        
        # 记录当前请求
        self.clients[client_id].append(current_time)
        
        # 处理请求
        response = await call_next(request)
        return response
