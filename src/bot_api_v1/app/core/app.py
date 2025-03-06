
import logging
import time
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio

from bot_api_v1.app.middlewares.logging_middleware import log_middleware
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.exceptions import http_exception_handler, CustomException
from bot_api_v1.app.api.main import router as api_router
from bot_api_v1.app.api.system import router as system_router
from bot_api_v1.app.middlewares.logging_middleware import wait_for_log_tasks
from bot_api_v1.app.db.init_db import init_db, wait_for_db
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.middlewares.rate_limit import RateLimitMiddleware

# def create_app():
#     """创建并配置FastAPI应用"""
#     app = FastAPI(
#         title=settings.PROJECT_NAME,
#         description="高性能API服务",
#         version=settings.VERSION,
#         docs_url=None if settings.ENVIRONMENT == "production" else "/api/docs",
#         redoc_url=None if settings.ENVIRONMENT == "production" else "/api/redoc",
#     )
    
#     # 配置中间件
#     # 1. 添加日志中间件
#     app.middleware("http")(log_middleware)
    
#     # 2. 添加CORS中间件
#     if settings.CORS_ORIGINS:
#         app.add_middleware(
#             CORSMiddleware,
#             allow_origins=settings.CORS_ORIGINS,
#             allow_credentials=True,
#             allow_methods=["*"],
#             allow_headers=["*"],
#         )
    
#     # 3. 添加主机验证中间件
#     if settings.ENVIRONMENT == "production":
#         app.add_middleware(
#             TrustedHostMiddleware, 
#             allowed_hosts=settings.ALLOWED_HOSTS
#         )
    
#     # 4. 添加速率限制中间件
#     if settings.ENVIRONMENT == "production":
#         app.add_middleware(RateLimitMiddleware)
    
#     # 注册异常处理器
#     app.add_exception_handler(Exception, http_exception_handler)
#     app.add_exception_handler(CustomException, http_exception_handler)
    
#     # 注册路由
#     app.include_router(api_router, prefix=settings.API_PREFIX)
#     app.include_router(system_router, prefix="/system", tags=["system"])
    
#     # 添加启动事件处理器
#     @app.on_event("startup")
#     async def startup_event():
#         try:
#             # 等待数据库可用
#             if not await wait_for_db(
#                 max_retries=settings.DB_CONNECTION_RETRIES,
#                 interval=settings.DB_RETRY_INTERVAL
#             ):
#                 logger.error("Cannot connect to database, application may not function properly")
            
#             # 初始化数据库
#             await init_db()
            
#             # 仅在开发环境中创建测试数据
#             if settings.ENVIRONMENT == "development" and settings.CREATE_TEST_DATA:
#                 await create_test_data()
                
#             logger.info(f"Application startup completed in {settings.ENVIRONMENT} environment")
#         except Exception as e:
#             logger.error(f"Error during startup: {str(e)}", exc_info=True)
#             # 在严重错误时，可能需要终止应用
#             if settings.ENVIRONMENT == "production":
#                 logger.critical("Critical startup error in production, exiting")
#                 import sys
#                 sys.exit(1)
    
#     # 添加关闭事件处理器
#     @app.on_event("shutdown")
#     async def shutdown_event():
#         logger.info("Application shutdown initiated")
#         # 等待日志任务完成
#         await wait_for_log_tasks()
#         logger.info("Application shutdown completed")
    
#     return app


from fastapi import FastAPI
from bot_api_v1.app.middlewares.logging_middleware import log_middleware
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.exceptions import http_exception_handler, CustomException
from bot_api_v1.app.middlewares.logging_middleware import wait_for_log_tasks

def create_app():
    """创建并配置FastAPI应用"""
    app = FastAPI(
        title="High Performance API",
        description="高性能API服务",
        version="1.0.0",
    )
    
    # 配置中间件
    app.middleware("http")(log_middleware)
    
    # 注册异常处理器
    app.add_exception_handler(Exception, http_exception_handler)
    
    # 添加健康检查路由
    @app.get("/health", tags=["health"])
    async def health_check():
        """系统健康检查"""
        return {
            "status": "ok",
            "version": "1.0.0",
            "environment": "development"
        }
    
    # 添加启动事件处理器
    @app.on_event("startup")
    async def startup_event():
        logger.info("Application startup completed")
    
    # 添加关闭事件处理器
    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Application shutdown initiated")
        # 等待日志任务完成
        await wait_for_log_tasks()
        logger.info("Application shutdown completed")
    
    return app
