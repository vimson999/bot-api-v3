from fastapi import APIRouter, Depends

from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse, Response

from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig
import os
import time
import torch  # 如果需要检查音频服务
from bot_api_v1.app.core.config import settings 
from bot_api_v1.app.services.business.wechat_service import WechatService
import xml.etree.ElementTree as ET
from typing import Dict, Optional
import requests


router = APIRouter(tags=["System Monitoring"])

@router.get("/health", 
           response_model=BaseResponse)
@TollgateConfig(
    title="系统健康检查", 
    type="health",
    base_tollgate="10",
    current_tollgate="1",
    plat="system"
)
async def health_check(
    db: AsyncSession = Depends(get_db)  # 异步数据库会话依赖注入
):
    """
    系统健康检查端点，验证各组件状态
    """
    start_time = time.time()
    components = {}
    has_error = False
    
    # 检查数据库连接
    try:
        # 使用 scalar_one_or_none() 替代 fetchone()
        result = await db.scalar(text("SELECT 1"))
        components["database"] = "healthy" if result is not None else "error"
    except Exception as e:
        logger.error(f"数据库健康检查异常: {str(e)}")
        components["database"] = "error"
        has_error = True
    
    # 检查缓存服务
    try:
        # TODO: 实现缓存服务检查
        components["cache"] = "healthy"
    except Exception:
        components["cache"] = "error"
        has_error = True
    
    # 检查音频服务
    try:
        # 简单检查音频服务是否可用
        components["audio_service"] = "healthy" if torch.cuda.is_available() else "degraded"
    except Exception:
        components["audio_service"] = "unknown"
    
    # 系统信息
    system_info = {
        "version": "1.0.0",  # 从配置获取
        "environment": os.environ.get("ENV", "development"),
        "response_time": f"{(time.time() - start_time) * 1000:.2f}ms"
    }
    
    # 确定整体状态
    if has_error:
        status = "degraded"
        status_code = 503
        message = "服务部分可用"
    else:
        status = "healthy"
        status_code = 200
        message = "服务正常运行"
    
    return BaseResponse(
        code=status_code,
        message=message,
        data={
            "status": status,
            "components": components,
            **system_info
        }
    )


#增加一个测试方法
@router.get("/test",
    response_model=BaseResponse)
async def test():
    from bot_api_v1.app.tasks.celery_tasks import add, print_message, long_running_task
    import time

    print("开始触发 Celery 任务...")

    # 1. 触发 add 任务
    # .delay() 是 apply_async() 的快捷方式，用于发送任务到队列
    result_add = add.delay(15, 27) 
    logger.info(f"  - 触发了 add(15, 27)，任务 ID: {result_add.id}")

    # 2. 触发 print_message 任务
    result_print = print_message.delay("你好 Celery!")
    print(f"  - 触发了 print_message，任务 ID: {result_print.id}")

    # 3. 触发 long_running_tas`k 任务
    result_long = long_running_task.delay(8) # 让它运行 8 秒
    logger.info(f"  - 触发了 long_running_task(8)，任务 ID: {result_long.id}")

    logger.info("\n所有任务已发送到队列。请观察 Celery Worker 的日志输出。")

    # 我们可以尝试获取第一个任务的结果 (可选)
    # 注意：这会阻塞，直到任务完成并返回结果
    logger.info("\n等待 add 任务的结果...")
    try:
        # result_add.get() 会等待任务完成并返回结果
        # 设置 timeout 防止无限等待 (例如 10 秒)
        add_task_return_value = result_add.get(timeout=10) 
        logger.info(f"  - add 任务的结果是: {add_task_return_value}")
    except Exception as e:
        logger.info(f"  - 获取 add 任务结果时出错或超时: {e}")
        logger.info(f"  - add 任务当前状态: {result_add.state}")

    logger.info("\n测试脚本执行完毕。")
    return BaseResponse(
        code=200,
        message="测试成功",
    )

