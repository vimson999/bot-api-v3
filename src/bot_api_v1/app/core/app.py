from fastapi import FastAPI, Depends

from bot_api_v1.app.middlewares.logging_middleware import log_middleware
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.exceptions import http_exception_handler
from bot_api_v1.app.core.dependencies import get_settings
from bot_api_v1.app.api.main import router as api_router
from bot_api_v1.app.api.routers.health import router as health_router
# from bot_api_v1.app.tasks import init_tasks  # 假设你会在tasks目录中创建这个函数

def create_app():
    app = FastAPI(
        title="High Performance API",
        description="高并发高性能API服务",
        version="1.0.0",
        dependencies=[Depends(get_settings)]
    )
    
    # 注册中间件（必须第一个注册）
    app.middleware("http")(log_middleware)
    
    # 注册异常处理器
    app.add_exception_handler(Exception, http_exception_handler)
    
    # 注册路由
    app.include_router(api_router, prefix="/api")
    # app.include_router(health_router, tags=["health"])  # 单独导入健康检查路由
    
    # 初始化异步任务
    # init_tasks()
    
    # 修正启动日志
    logger.info("Application startup completed", extra={
        "request_id": "system",
        "headers": {}
    })
    
    return app
