# bot_api_v1/app/tasks/base.py

import asyncio
from typing import Callable, Dict, Any, Optional, List
import logging
import time
import traceback
import uuid
from datetime import datetime
from functools import wraps

logger = logging.getLogger(__name__)

# 全局任务注册表
_TASK_REGISTRY = {}

def register_task(name: str, coro, timeout: Optional[int] = None):
    """
    注册一个异步任务
    
    Args:
        name: 任务的唯一标识名
        coro: 异步协程
        timeout: 任务超时时间（秒），None表示无超时
    
    Returns:
        task_id: 任务ID
    """
    task_id = str(uuid.uuid4())
    
    task = asyncio.create_task(coro)
    
    # 添加任务到注册表
    _TASK_REGISTRY[task_id] = {
        "name": name,
        "task": task,
        "created_at": datetime.now(),
        "status": "running",
        "timeout": timeout,
    }
    
    # 设置回调以在完成时更新状态
    def _on_task_done(task):
        if task_id in _TASK_REGISTRY:
            if task.exception():
                _TASK_REGISTRY[task_id]["status"] = "failed"
                _TASK_REGISTRY[task_id]["error"] = str(task.exception())
                logger.error(f"Task {name}({task_id}) failed: {str(task.exception())}")
                logger.error(traceback.format_exception(None, task.exception(), None))
            else:
                _TASK_REGISTRY[task_id]["status"] = "completed"
                _TASK_REGISTRY[task_id]["completed_at"] = datetime.now()
                logger.debug(f"Task {name}({task_id}) completed successfully")
    
    task.add_done_callback(_on_task_done)
    
    # 如果设置了超时，添加超时处理
    if timeout:
        async def _check_timeout():
            await asyncio.sleep(timeout)
            if task_id in _TASK_REGISTRY and _TASK_REGISTRY[task_id]["status"] == "running":
                task.cancel()
                _TASK_REGISTRY[task_id]["status"] = "timeout"
                logger.warning(f"Task {name}({task_id}) timed out after {timeout} seconds")
                
        asyncio.create_task(_check_timeout())
    
    logger.debug(f"Task {name}({task_id}) registered")
    return task_id

def task_decorator(name: str = None, timeout: Optional[int] = None):
    """
    异步任务装饰器
    
    Args:
        name: 任务名称，默认使用函数名
        timeout: 超时时间（秒）
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            task_name = name or func.__name__
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                logger.debug(f"Task {task_name} completed in {duration:.2f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"Task {task_name} failed after {duration:.2f}s: {str(e)}")
                raise
                
        return wrapper
    return decorator

async def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """
    获取任务状态
    
    Args:
        task_id: 任务ID
        
    Returns:
        task_info: 任务信息字典，不存在则返回None
    """
    return _TASK_REGISTRY.get(task_id)

async def cancel_task(task_id: str) -> bool:
    """
    取消任务
    
    Args:
        task_id: 任务ID
        
    Returns:
        success: 是否成功取消
    """
    if task_id in _TASK_REGISTRY and _TASK_REGISTRY[task_id]["status"] == "running":
        task = _TASK_REGISTRY[task_id]["task"]
        task.cancel()
        _TASK_REGISTRY[task_id]["status"] = "cancelled"
        logger.info(f"Task {_TASK_REGISTRY[task_id]['name']}({task_id}) cancelled")
        return True
    return False

async def cleanup_completed_tasks(max_age: int = 3600):
    """
    清理已完成的任务
    
    Args:
        max_age: 完成任务保留的最长时间（秒）
    """
    now = datetime.now()
    to_remove = []
    
    for task_id, task_info in _TASK_REGISTRY.items():
        if task_info["status"] in ["completed", "failed", "cancelled", "timeout"]:
            completed_at = task_info.get("completed_at", task_info["created_at"])
            age = (now - completed_at).total_seconds()
            if age > max_age:
                to_remove.append(task_id)
    
    for task_id in to_remove:
        del _TASK_REGISTRY[task_id]
    
    if to_remove:
        logger.debug(f"Cleaned up {len(to_remove)} completed tasks")

async def wait_for_tasks():
    """等待所有运行中的任务完成"""
    running_tasks = [
        info["task"] for info in _TASK_REGISTRY.values() 
        if info["status"] == "running"
    ]
    
    if running_tasks:
        logger.info(f"Waiting for {len(running_tasks)} running tasks to complete...")
        await asyncio.gather(*running_tasks, return_exceptions=True)
        logger.info("All tasks completed")
