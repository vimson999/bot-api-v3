from fastapi import FastAPI
from bot_api_v1.app.middlewares.logging_middleware import log_middleware
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.exceptions import global_exception_handler
from bot_api_v1.app.api.main import router as api_router
def create_app():
    app = FastAPI(title="High Performance API")
    
    # 注册中间件（必须第一个注册）
    app.middleware("http")(log_middleware)



    app.add_exception_handler(Exception, global_exception_handler)

    app.include_router(api_router, prefix="/api")

     # 修正启动日志
    logger.info("Application startup completed", extra={
        "request_id": "system",
        "headers": {}
    })
    return app