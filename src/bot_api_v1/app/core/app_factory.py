import logging
import time
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio
from fastapi.staticfiles import StaticFiles

from bot_api_v1.app.middlewares.logging_middleware import log_middleware
from bot_api_v1.app.middlewares.request_counter import add_request_counter
from bot_api_v1.app.core.logger import logger,db_log_sink
from bot_api_v1.app.core.exceptions import http_exception_handler, CustomException
from bot_api_v1.app.api.main import router as api_router
from bot_api_v1.app.tasks.base import wait_for_tasks, wait_for_log_tasks, TASK_TYPE_LOG
from bot_api_v1.app.db.init_db import init_db, wait_for_db
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.middlewares.rate_limit import RateLimitMiddleware
from bot_api_v1.app.api.routers import script
from bot_api_v1.app.api.routers import wechat_mp  # Import the media route

# from bot_api_v1.app.monitoring import setup_metrics, metrics_middleware, start_system_metrics_collector
from bot_api_v1.app.api.routers import wechat  # Import the wechat router
from bot_api_v1.app.services.business.wechat_service import WechatService  # 添加这行导入
import os

# 挂载静态文件目录

# 找到项目根目录（假设是包含src的目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
static_directory = os.path.join(project_root, "src", "bot_api_v1", "app", "static")


def create_app():
    """创建并配置FastAPI应用"""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="高性能API服务",
        version=settings.VERSION,
        docs_url="/docs",  # Swagger UI 路径
        redoc_url="/redoc",  # ReDoc 路径
        openapi_url="/openapi.json",  # OpenAPI JSON文档路径
    )

    # 1. 添加日志中间件
    app.middleware("http")(log_middleware)

    # 2. 添加CORS中间件
    # if settings.CORS_ORIGINS:
    #     app.add_middleware(
    #         CORSMiddleware,
    #         allow_origins=settings.CORS_ORIGINS,
    #         allow_credentials=True,
    #         allow_methods=["*"],
    #         allow_headers=["*"],
    #     )
    
    # # 3. 添加主机验证中间件
    # if settings.ENVIRONMENT == "production":
    #     app.add_middleware(
    #         TrustedHostMiddleware, 
    #         allowed_hosts=settings.ALLOWED_HOSTS
    #     )

    # # 4. 添加速率限制中间件
    # if settings.ENVIRONMENT == "production":
    #     app.add_middleware(RateLimitMiddleware)



    # 5. 添加请求计数中间件
    # add_request_counter(app)
    
    # # 6. 添加Prometheus指标中间件
    # metrics_middleware(app)



    # 注册路由
    app.include_router(api_router, prefix=settings.API_PREFIX)
    app.include_router(script.router, prefix="/script")
    app.include_router(wechat.router, prefix="/wechat")
    app.include_router(wechat_mp.router, prefix="/wechat_mp")

    # 添加新的媒体路由
    from bot_api_v1.app.api.routers import media
    app.include_router(media.router, prefix="/media")



    logger.info(f"项目根目录: {project_root}")
    logger.info(f"尝试挂载静态文件目录: {static_directory}")

    # 确保目录存在再挂载
    if os.path.exists(static_directory):
        app.mount("/static", StaticFiles(directory=static_directory), name="static")
    else:
        logger.error(f"静态文件目录不存在: {static_directory}")


    # 注册异常处理器
    app.add_exception_handler(Exception, http_exception_handler)
    
    # 初始化Prometheus指标
    # setup_metrics(app, app_name=settings.PROJECT_NAME)
    
    # # 启动系统指标收集
    # start_system_metrics_collector(app)

    # 添加启动事件处理器
    @app.on_event("startup")
    async def startup_event():
        try:
            # 记录应用启动时间
            app.state.startup_time = time.time()
            
            # 初始化请求计数器
            app.state.request_counts = {
                "total": 0,
                "success": 0,
                "error": 0,
                "by_endpoint": {},
                "by_method": {}
            }
            
            

            # 等待数据库可用
            if not await wait_for_db(
                max_retries=settings.DB_CONNECT_RETRIES,
                interval=settings.DB_CONNECT_RETRY_INTERVAL
            ):
                logger.error("Cannot connect to database, application may not function properly")
            

            # 初始化微信服务实例
            # app.state.wechat_service = WechatService()
            # if settings.CURRENT_WECHAT_MP_MENU_VERSION < settings.TARGET_WECHAT_MP_MENU_VERSION:
            #     try:
            #         access_token = await app.state.wechat_service._get_mp_access_token()
            #         await app.state.wechat_service.create_wechat_menu(access_token)
                    
            #         # 直接更新设置值
            #         settings.CURRENT_WECHAT_MP_MENU_VERSION = settings.TARGET_WECHAT_MP_MENU_VERSION
                    
            #         logger.info_to_db(f"成功创建微信公众号菜单,微信菜单已更新到版本 {settings.TARGET_WECHAT_MP_MENU_VERSION}")
            #     except Exception as e:
            #         logger.error(f"更新微信菜单失败: {str(e)}")

            # 初始化数据库
            # await init_db()
            
            # 仅在开发环境中创建测试数据
            # if settings.ENVIRONMENT == "development" and settings.CREATE_TEST_DATA:
            #     await create_test_data()

            loop = asyncio.get_running_loop()
            db_log_sink.start(loop) # 启动消费者
                
            logger.info(f"Application startup completed in {settings.ENVIRONMENT} environment")
        except Exception as e:
            logger.error(f"Error during startup: {str(e)}", exc_info=True)
            # 在严重错误时，可能需要终止应用
            if settings.ENVIRONMENT == "production":
                logger.critical("Critical startup error in production, exiting")
                import sys
                sys.exit(1)

    # 添加关闭事件处理器
    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Application shutdown initiated")
        
        try:
            # 首先等待日志任务完成 - 使用较短的超时时间
            logger.info("Waiting for log tasks to complete...")
            await wait_for_log_tasks(timeout=5)  # 日志任务等待5秒
            
            # 然后等待其他所有任务完成 - 可以使用较长的超时时间
            logger.info("Waiting for all remaining tasks to complete...")
            await wait_for_tasks(timeout=30)  # 其他任务等待30秒
            
            await db_log_sink.stop() # 优雅停止
            logger.info("All tasks completed successfully")
        except Exception as e:
            logger.error(f"Error during task shutdown: {str(e)}", exc_info=True)
        
        logger.info("Application shutdown completed")
    
    return app

