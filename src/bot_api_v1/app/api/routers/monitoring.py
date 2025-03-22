"""
监控相关的API路由

提供系统健康检查、性能指标和各种监控端点
"""
from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import psutil
import platform
import time
import os
import datetime

from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.db.session import get_db
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig
from bot_api_v1.app.tasks.base import get_task_statistics

router = APIRouter(tags=["监控"])

@router.get(
    "/health/detailed", 
    response_model=BaseResponse,
    description="详细的系统健康状态",
    summary="获取系统详细健康状态"
)
@TollgateConfig(
    title="详细健康检查", 
    type="health",
    base_tollgate="10",
    current_tollgate="1",
    plat="system"
)
async def detailed_health_check(
    request: Request,
    db: AsyncSession = Depends(get_db),
    bg_tasks: BackgroundTasks = None
):
    """
    详细的系统健康检查
    
    检查所有系统组件的健康状态，包括:
    - 数据库连接
    - 文件系统
    - 内存使用
    - CPU使用
    - 异步任务状态
    """
    start_time = time.time()
    components = {}
    has_error = False
    
    # 检查数据库连接
    try:
        # 使用 scalar_one_or_none() 替代 fetchone()
        result = await db.scalar(text("SELECT 1"))
        components["database"] = {
            "status": "healthy" if result is not None else "error",
            "details": {
                "result": result
            }
        }
    except Exception as e:
        logger.error(f"数据库健康检查异常: {str(e)}")
        components["database"] = {
            "status": "error",
            "details": {
                "error": str(e)
            }
        }
        has_error = True
    
    # 检查文件系统
    try:
        disk = psutil.disk_usage('/')
        components["disk"] = {
            "status": "healthy" if disk.percent < 90 else "warning",
            "details": {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": disk.percent
            }
        }
        if disk.percent > 95:
            components["disk"]["status"] = "error"
            has_error = True
    except Exception as e:
        logger.error(f"文件系统健康检查异常: {str(e)}")
        components["disk"] = {
            "status": "error",
            "details": {
                "error": str(e)
            }
        }
        has_error = True
    
    # 检查内存
    try:
        memory = psutil.virtual_memory()
        components["memory"] = {
            "status": "healthy" if memory.percent < 90 else "warning",
            "details": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "percent": memory.percent
            }
        }
        if memory.percent > 95:
            components["memory"]["status"] = "error"
            has_error = True
    except Exception as e:
        logger.error(f"内存健康检查异常: {str(e)}")
        components["memory"] = {
            "status": "error",
            "details": {
                "error": str(e)
            }
        }
        has_error = True
    
    # 检查CPU
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        components["cpu"] = {
            "status": "healthy" if cpu_percent < 80 else "warning",
            "details": {
                "percent": cpu_percent,
                "count": psutil.cpu_count(),
                "load_avg": os.getloadavg() if hasattr(os, 'getloadavg') else None
            }
        }
        if cpu_percent > 95:
            components["cpu"]["status"] = "error"
            has_error = True
    except Exception as e:
        logger.error(f"CPU健康检查异常: {str(e)}")
        components["cpu"] = {
            "status": "error",
            "details": {
                "error": str(e)
            }
        }
        has_error = True
    
    # 检查异步任务状态
    try:
        task_stats = await get_task_statistics()
        components["tasks"] = {
            "status": "healthy",
            "details": task_stats
        }
        
        # 如果有太多正在运行的任务，可能表示问题
        running_tasks = task_stats.get("status_counts", {}).get("running", 0)
        if running_tasks > 100:
            components["tasks"]["status"] = "warning"
        if running_tasks > 500:
            components["tasks"]["status"] = "error"
            has_error = True
    except Exception as e:
        logger.error(f"任务健康检查异常: {str(e)}")
        components["tasks"] = {
            "status": "error",
            "details": {
                "error": str(e)
            }
        }
        has_error = True
    
    # 系统信息
    system_info = {
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "os": platform.system(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "response_time": f"{(time.time() - start_time) * 1000:.2f}ms",
        "startup_time": getattr(request.app.state, "startup_time", None),
        "uptime_seconds": round(time.time() - getattr(request.app.state, "startup_time", time.time())),
    }
    
    # 确定整体状态
    if has_error:
        status = "error"
        status_code = 503
        message = "系统出现错误"
    elif any(c["status"] == "warning" for c in components.values()):
        status = "warning"
        status_code = 200
        message = "系统运行中，但有潜在问题"
    else:
        status = "healthy"
        status_code = 200
        message = "系统运行正常"
    
    # 如果有后台任务，可以异步记录健康检查结果
    if bg_tasks:
        bg_tasks.add_task(
            log_health_check_result, 
            status=status, 
            components=components
        )
    
    return BaseResponse(
        code=status_code,
        message=message,
        data={
            "status": status,
            "components": components,
            "system": system_info,
            "timestamp": datetime.datetime.now().isoformat()
        }
    )

@router.get(
    "/metrics/summary", 
    response_model=BaseResponse,
    description="系统指标摘要",
    summary="获取系统指标摘要"
)
@TollgateConfig(
    title="系统指标摘要", 
    type="metrics",
    base_tollgate="10",
    current_tollgate="1",
    plat="system"
)
async def metrics_summary(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    获取系统指标摘要
    
    包括:
    - CPU使用率
    - 内存使用率
    - 磁盘使用率
    - 数据库连接池状态
    - 请求速率
    - 错误率
    """
    try:
        # 收集基本性能指标
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # 尝试从请求应用状态获取请求计数器
        request_counts = getattr(request.app.state, "request_counts", {})
        
        # 收集数据库连接池信息
        db_stats = {}
        try:
            if hasattr(db.get_bind(), "pool"):
                pool = db.get_bind().pool
                db_stats = {
                    "pool_size": pool.size(),
                    "checkedout": pool.checkedout(),
                    "overflow": pool.overflow(),
                    "checkedin": pool.checkedin()
                }
        except Exception as e:
            logger.error(f"获取数据库统计信息失败: {str(e)}")
            db_stats = {"error": str(e)}
        
        # 构建响应
        return BaseResponse(
            code=200,
            message="成功获取系统指标摘要",
            data={
                "system": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": round(memory.available / (1024**3), 2),
                    "disk_percent": disk.percent,
                    "disk_free_gb": round(disk.free / (1024**3), 2),
                    "process_count": len(psutil.pids()),
                    "open_files": len(psutil.Process().open_files()),
                    "connections": len(psutil.Process().connections())
                },
                "database": db_stats,
                "requests": request_counts,
                "tasks": await get_task_statistics(),
                "timestamp": datetime.datetime.now().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"获取系统指标摘要失败: {str(e)}")
        return BaseResponse(
            code=500,
            message=f"获取系统指标摘要失败: {str(e)}",
            data=None
        )

async def log_health_check_result(status: str, components: dict):
    """
    记录健康检查结果
    
    Args:
        status: 整体健康状态
        components: 各组件的健康信息
    """
    try:
        log_level = "info" if status == "healthy" else "warning" if status == "warning" else "error"
        getattr(logger, log_level)(
            f"系统健康检查: {status}",
            extra={
                "health_check": {
                    "status": status,
                    "components": components
                }
            }
        )
    except Exception as e:
        logger.error(f"记录健康检查结果失败: {str(e)}")

# 导入设置
from bot_api_v1.app.core.config import settings