# bot_api_v1/app/tasks/base.py

import asyncio
from typing import Callable, Dict, Any, Optional, List, Set, Union
import logging
import time
import traceback
import uuid
from datetime import datetime
from functools import wraps

logger = logging.getLogger(__name__)

# 全局任务注册表
_TASK_REGISTRY = {}

# 任务注册表大小限制
MAX_TASK_REGISTRY_SIZE = 10000  # 可以根据服务器内存和实际需求调整
CLEANUP_THRESHOLD = MAX_TASK_REGISTRY_SIZE * 0.8

# 默认任务超时时间（秒）
DEFAULT_TASK_TIMEOUT = 3600  # 1小时

# 日志类任务超时时间（秒）
LOG_TASK_TIMEOUT = 60  # 1分钟

# 日志任务最大保留时间（秒）
LOG_TASK_MAX_AGE = 600  # 10分钟

# 是否已启动清理任务
_cleanup_task_started = False

# 任务类型
TASK_TYPE_GENERAL = "general"  # 一般任务
TASK_TYPE_LOG = "log"          # 日志任务


def register_task(name: str, coro, timeout: Optional[int] = None, task_type: str = TASK_TYPE_GENERAL):
    """
    注册一个异步任务
    
    Args:
        name: 任务的唯一标识名
        coro: 异步协程
        timeout: 任务超时时间（秒），None表示使用默认值
        task_type: 任务类型，用于分类和差异化处理
    
    Returns:
        task_id: 任务ID
    """
    global _cleanup_task_started
    
    # 检查注册表大小，如果超过阈值则触发紧急清理
    if len(_TASK_REGISTRY) > CLEANUP_THRESHOLD:
        asyncio.create_task(emergency_cleanup())
    
    # 如果还未启动定期清理任务，启动它
    if not _cleanup_task_started:
        asyncio.create_task(scheduled_cleanup())
        _cleanup_task_started = True
    
    task_id = str(uuid.uuid4())
    
    # 设置任务超时时间
    if timeout is None:
        if task_type == TASK_TYPE_LOG:
            timeout = LOG_TASK_TIMEOUT
        else:
            timeout = DEFAULT_TASK_TIMEOUT
    
    # 创建异步任务
    task = asyncio.create_task(coro)
    
    # 添加任务到注册表
    _TASK_REGISTRY[task_id] = {
        "name": name,
        "task": task,
        "created_at": datetime.now(),
        "status": "running",
        "timeout": timeout,
        "type": task_type,
    }
    
    # 设置回调以在完成时更新状态
    def _on_task_done(task):
        if task_id in _TASK_REGISTRY:
            if task.cancelled():
                _TASK_REGISTRY[task_id]["status"] = "cancelled"
                _TASK_REGISTRY[task_id]["completed_at"] = datetime.now()
                logger.debug(f"Task {name}({task_id}) was cancelled")
            elif task.exception():
                _TASK_REGISTRY[task_id]["status"] = "failed"
                _TASK_REGISTRY[task_id]["error"] = str(task.exception())
                _TASK_REGISTRY[task_id]["completed_at"] = datetime.now()
                
                # 对于日志任务，使用debug级别记录错误，避免错误日志爆炸
                if task_type == TASK_TYPE_LOG:
                    logger.debug(f"Log task {name}({task_id}) failed: {str(task.exception())}")
                else:
                    logger.error(f"Task {name}({task_id}) failed: {str(task.exception())}")
                    logger.error(traceback.format_tb(task.exception().__traceback__))
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
                _TASK_REGISTRY[task_id]["completed_at"] = datetime.now()
                
                # 对于日志任务，使用debug级别记录超时，减少噪音
                if task_type == TASK_TYPE_LOG:
                    logger.debug(f"Log task {name}({task_id}) timed out after {timeout} seconds")
                else:
                    logger.warning(f"Task {name}({task_id}) timed out after {timeout} seconds")
                
        asyncio.create_task(_check_timeout())
    
    # 根据任务类型使用不同级别的日志
    if task_type == TASK_TYPE_LOG:
        logger.debug(f"Log task {name}({task_id}) registered")
    else:
        logger.debug(f"Task {name}({task_id}) registered")
        
    return task_id


async def emergency_cleanup():
    """当任务注册表过大时紧急清理"""
    logger.warning(f"Task registry size ({len(_TASK_REGISTRY)}) exceeded threshold, performing emergency cleanup")
    
    # 首先清理所有完成的日志任务，因为这些通常是最不重要的
    log_tasks = [
        task_id for task_id, info in _TASK_REGISTRY.items()
        if info.get("type") == TASK_TYPE_LOG and info["status"] != "running"
    ]
    
    # 然后清理其他非运行状态的任务
    non_running = [
        task_id for task_id, info in _TASK_REGISTRY.items()
        if info["status"] != "running" and task_id not in log_tasks
    ]
    
    to_clean = log_tasks + non_running
    
    # 如果清理非运行状态的任务后仍然太大，则考虑清理一部分运行中的日志任务
    if len(_TASK_REGISTRY) - len(to_clean) > CLEANUP_THRESHOLD:
        running_log_tasks = [
            (task_id, info) for task_id, info in _TASK_REGISTRY.items()
            if info.get("type") == TASK_TYPE_LOG and info["status"] == "running"
        ]
        
        # 按创建时间排序
        running_log_tasks.sort(key=lambda x: x[1]["created_at"])
        
        # 取最旧的30%运行中日志任务取消它们
        oldest_count = max(1, int(len(running_log_tasks) * 0.3))
        for task_id, info in running_log_tasks[:oldest_count]:
            logger.warning(f"Emergency cancelling old log task {info['name']}({task_id})")
            try:
                info["task"].cancel()
                info["status"] = "cancelled_emergency"
                info["completed_at"] = datetime.now()
                to_clean.append(task_id)
            except Exception as e:
                logger.error(f"Failed to cancel log task {task_id}: {str(e)}")
    
    # 如果清理日志任务后仍然太大，则考虑清理一部分运行中的普通任务
    if len(_TASK_REGISTRY) - len(to_clean) > CLEANUP_THRESHOLD:
        running_general_tasks = [
            (task_id, info) for task_id, info in _TASK_REGISTRY.items()
            if info.get("type") != TASK_TYPE_LOG and info["status"] == "running"
        ]
        
        # 按创建时间排序
        running_general_tasks.sort(key=lambda x: x[1]["created_at"])
        
        # 取最旧的20%运行中普通任务取消它们
        oldest_count = max(1, int(len(running_general_tasks) * 0.2))
        for task_id, info in running_general_tasks[:oldest_count]:
            logger.warning(f"Emergency cancelling old general task {info['name']}({task_id})")
            try:
                info["task"].cancel()
                info["status"] = "cancelled_emergency"
                info["completed_at"] = datetime.now()
                to_clean.append(task_id)
            except Exception as e:
                logger.error(f"Failed to cancel general task {task_id}: {str(e)}")
    
    # 删除所有标记的任务
    removed_count = 0
    for task_id in to_clean:
        try:
            del _TASK_REGISTRY[task_id]
            removed_count += 1
        except KeyError:
            pass  # 任务可能已被其他进程移除
    
    logger.info(f"Emergency cleanup removed {removed_count} tasks, registry size now {len(_TASK_REGISTRY)}")


async def scheduled_cleanup():
    """定期执行清理任务"""
    try:
        while True:
            # 每小时执行一次普通清理
            await asyncio.sleep(3600)
            
            # 首先清理日志任务（保留时间更短）
            await cleanup_tasks_by_type(TASK_TYPE_LOG, LOG_TASK_MAX_AGE)
            
            # 然后清理普通任务
            await cleanup_tasks_by_type(TASK_TYPE_GENERAL, 3600 * 24)  # 24小时
            
            logger.info(f"Scheduled cleanup completed, registry size: {len(_TASK_REGISTRY)}")
    except asyncio.CancelledError:
        logger.info("Scheduled cleanup task cancelled")
    except Exception as e:
        logger.error(f"Error in scheduled cleanup: {str(e)}", exc_info=True)


def task_decorator(name: str = None, timeout: Optional[int] = None, task_type: str = TASK_TYPE_GENERAL):
    """
    异步任务装饰器
    
    Args:
        name: 任务名称，默认使用函数名
        timeout: 超时时间（秒）
        task_type: 任务类型
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            task_name = name or func.__name__
            start_time = time.time()
            
            # 创建任务上下文字典，用于记录任务执行的相关信息
            task_context = {
                "name": task_name,
                "args": str(args),
                "kwargs": str(kwargs),
                "start_time": start_time
            }
            
            try:
                # 执行实际任务函数
                result = await func(*args, **kwargs)
                
                # 记录成功信息
                duration = time.time() - start_time
                logger.debug(f"Task {task_name} completed in {duration:.2f}s")
                
                # 返回结果
                return result
            except Exception as e:
                # 记录失败信息
                duration = time.time() - start_time
                logger.error(f"Task {task_name} failed after {duration:.2f}s: {str(e)}")
                
                # 再次抛出异常以便上层处理
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
    if task_id not in _TASK_REGISTRY:
        return None
        
    task_info = _TASK_REGISTRY[task_id].copy()
    
    # 移除task对象，避免JSON序列化问题
    if "task" in task_info:
        del task_info["task"]
        
    return task_info


async def cancel_task(task_id: str) -> bool:
    """
    取消任务
    
    Args:
        task_id: 任务ID
        
    Returns:
        success: 是否成功取消
    """
    if task_id in _TASK_REGISTRY and _TASK_REGISTRY[task_id]["status"] == "running":
        try:
            task = _TASK_REGISTRY[task_id]["task"]
            task.cancel()
            _TASK_REGISTRY[task_id]["status"] = "cancelled"
            _TASK_REGISTRY[task_id]["completed_at"] = datetime.now()
            logger.info(f"Task {_TASK_REGISTRY[task_id]['name']}({task_id}) cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {str(e)}")
            return False
    return False


async def cleanup_tasks_by_type(task_type: str, max_age: int):
    """
    清理指定类型的已完成任务
    
    Args:
        task_type: 任务类型
        max_age: 完成任务保留的最长时间（秒）
    """
    now = datetime.now()
    to_remove = []
    
    for task_id, task_info in _TASK_REGISTRY.items():
        # 检查任务类型是否匹配
        if task_info.get("type") != task_type:
            continue
            
        if task_info["status"] in ["completed", "failed", "cancelled", "timeout", "cancelled_emergency"]:
            if "completed_at" in task_info:
                age = (now - task_info["completed_at"]).total_seconds()
                if age > max_age:
                    to_remove.append(task_id)
            else:
                # 如果没有完成时间，使用创建时间
                age = (now - task_info["created_at"]).total_seconds()
                if age > max_age * 2:  # 对于异常情况，使用更长的保留时间
                    to_remove.append(task_id)
    
    removed_count = 0
    for task_id in to_remove:
        try:
            del _TASK_REGISTRY[task_id]
            removed_count += 1
        except KeyError:
            pass  # 任务可能已被其他进程移除
    
    if removed_count > 0:
        logger.debug(f"Cleaned up {removed_count} {task_type} tasks")


async def cleanup_completed_tasks(max_age: int = 3600):
    """
    清理所有已完成的任务 (兼容旧版本API)
    
    Args:
        max_age: 完成任务保留的最长时间（秒）
    """
    # 清理所有类型的任务
    await cleanup_tasks_by_type(TASK_TYPE_LOG, min(max_age, LOG_TASK_MAX_AGE))
    await cleanup_tasks_by_type(TASK_TYPE_GENERAL, max_age)


async def get_task_statistics() -> Dict[str, Any]:
    """
    获取任务统计信息
    
    Returns:
        stats: 包含任务统计信息的字典
    """
    total = len(_TASK_REGISTRY)
    statuses = {}
    types = {}
    
    for info in _TASK_REGISTRY.values():
        # 按状态统计
        status = info["status"]
        statuses[status] = statuses.get(status, 0) + 1
        
        # 按类型统计
        task_type = info.get("type", TASK_TYPE_GENERAL)
        types[task_type] = types.get(task_type, 0) + 1
    
    return {
        "total_tasks": total,
        "status_counts": statuses,
        "type_counts": types,
        "registry_size_limit": MAX_TASK_REGISTRY_SIZE,
        "cleanup_threshold": CLEANUP_THRESHOLD
    }


async def wait_for_tasks(task_types: Optional[List[str]] = None, timeout: int = 30):
    """
    等待指定类型的运行中任务完成
    
    Args:
        task_types: 要等待的任务类型列表，None表示所有类型
        timeout: 最长等待时间（秒）
    """
    # 筛选符合条件的任务
    running_tasks = []
    for task_id, info in _TASK_REGISTRY.items():
        if info["status"] == "running":
            if task_types is None or info.get("type", TASK_TYPE_GENERAL) in task_types:
                running_tasks.append((task_id, info["task"]))
    
    if running_tasks:
        task_ids = [t[0] for t in running_tasks]
        tasks = [t[1] for t in running_tasks]
        
        logger.info(f"Waiting for {len(running_tasks)} tasks to complete...")
        
        try:
            # 设置超时
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            logger.info("All tasks completed successfully")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for tasks after {timeout}s")
            # 强制取消超时的任务
            for task_id, task in running_tasks:
                if not task.done():
                    task.cancel()
                    if task_id in _TASK_REGISTRY:
                        _TASK_REGISTRY[task_id]["status"] = "cancelled_shutdown"
                        _TASK_REGISTRY[task_id]["completed_at"] = datetime.now()
            logger.info("Cancelled remaining tasks")
        except Exception as e:
            logger.error(f"Error waiting for tasks: {str(e)}")


async def wait_for_log_tasks(timeout: int = 5):
    """等待所有日志任务完成，应用退出前调用"""
    await wait_for_tasks([TASK_TYPE_LOG], timeout)