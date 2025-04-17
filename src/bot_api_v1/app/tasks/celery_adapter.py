# bot_api_v1/app/tasks/celery_adapter.py
from typing import Optional, Dict, Any, Callable, Tuple
from celery import Celery
from celery.result import AsyncResult
from celery.exceptions import TaskRevokedError
import datetime

from bot_api_v1.app.core.logger import logger

# 导入同级目录下的 celery_app 实例
# 如果你的目录结构不同，请务必修改这里的导入路径
try:
    from .celery_app import celery_app
except ImportError:
    # 尝试从可能的根路径导入 (你需要根据实际情况调整)
    try:
         from bot_api_v1.app.tasks.celery_app import celery_app
    except ImportError:
        logger.error("无法导入 celery_app，请检查 celery_adapter.py 相对于 celery_app.py 的路径和你的 Python Path 设置。", exc_info=True)
        raise

# --- Celery 状态到旧 base.py 状态的映射 ---
CELERY_TO_OLD_STATUS = {
    'PENDING': 'running',
    'STARTED': 'running',
    'SUCCESS': 'completed',
    'FAILURE': 'failed',
    'RETRY': 'running',
    'REVOKED': 'cancelled',
}

# 默认任务超时时间（秒）- 用于 Celery 的软超时
DEFAULT_CELERY_SOFT_TIMEOUT = 3600  # 1小时
LOG_CELERY_SOFT_TIMEOUT = 60        # 1分钟

def register_task(
    name: str,
    task_func: Callable,
    args: Tuple = (),
    kwargs: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    task_type: str = "general"
) -> Optional[str]:
    """
    适配器函数：注册并发送一个 Celery 任务，模仿旧 base.py 的接口。
    """
    if kwargs is None:
        kwargs = {}

    if timeout is None:
        timeout = LOG_CELERY_SOFT_TIMEOUT if task_type == "log" else DEFAULT_CELERY_SOFT_TIMEOUT

    celery_task_name = getattr(task_func, 'name', name)
    # 获取 trace_id, 优先从 kwargs 获取，否则生成/获取默认值
    # 注意：这里无法访问 request_ctx，trace_id 需要从调用方传入 kwargs
    trace_id = kwargs.get("trace_id", "unknown_trace") # 假设 trace_id 在 kwargs 中传递
    log_extra = {"request_id": trace_id, "celery_task_func": celery_task_name}

    try:
        # 确定队列名
        queue_name = task_type if task_type != "general" else celery_app.conf.task_default_queue # 使用 Celery 默认队列名 'celery'
        
        async_result = task_func.apply_async(
            args=args,
            kwargs=kwargs,
            soft_time_limit=timeout,
            # time_limit=timeout + 60, # 可选硬超时
            queue=queue_name
        )
        task_id = async_result.id

        logger.info(f"Celery task '{celery_task_name}' ({task_id}) submitted to queue '{queue_name}'.", extra=log_extra)

        return task_id
    except Exception as e:
        logger.error(f"Failed to submit Celery task '{celery_task_name}': {e}", exc_info=True, extra=log_extra)
        return None


async def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """
    适配器函数：获取 Celery 任务的状态，模仿旧 base.py 的接口。
    """
    if not task_id:
        logger.warning("get_task_status called with empty task_id")
        return None

    log_extra = {"celery_task_id": task_id}

    try:
        result = AsyncResult(task_id, app=celery_app)
        celery_status = result.status
        status = CELERY_TO_OLD_STATUS.get(celery_status, celery_status.lower())

        task_info = {
            "task_id": task_id,
            "status": status,
            "completed_at": result.date_done,
            "error": None # 初始化
        }

        if result.failed():
            error_info = result.info
            if isinstance(error_info, Exception):
                 task_info["error"] = f"{type(error_info).__name__}: {str(error_info)}"
            else:
                 task_info["error"] = str(error_info)
            # task_info["traceback"] = result.traceback

        if task_info.get("completed_at") and isinstance(task_info["completed_at"], datetime.datetime):
             # 保持 datetime 对象，调用者如果需要再转换
             pass

        # 注意：这里不直接返回 result.result，因为它的结构由 Task 决定
        # 状态查询端点需要再次获取 result 并解析其内容

        logger.debug(f"Status for task {task_id}: {status}", extra=log_extra)
        return task_info

    except Exception as e:
        logger.error(f"Error getting status for Celery task {task_id}: {e}", exc_info=True, extra=log_extra)
        return {
            "task_id": task_id,
            "status": "error_fetching_status",
            "error": str(e)
        }

async def cancel_task(task_id: str) -> bool:
    """
    适配器函数：尝试取消 Celery 任务，模仿旧 base.py 的接口。
    """
    if not task_id:
        logger.warning("cancel_task called with empty task_id")
        return False

    log_extra = {"celery_task_id": task_id}
        
    try:
        result = AsyncResult(task_id, app=celery_app)
        if result.ready():
            logger.warning(f"Attempted to cancel task {task_id} which is already completed with status: {result.status}", extra=log_extra)
            return False

        celery_app.control.revoke(task_id, terminate=False, signal='SIGTERM')
        logger.info(f"Revoke command sent for Celery task {task_id} (terminate=False)", extra=log_extra)
        return True

    except Exception as e:
        logger.error(f"Error sending revoke command for Celery task {task_id}: {e}", exc_info=True, extra=log_extra)
        return False

# === 旧 base.py 功能的替代说明 ===
# cleanup_*: 由 Result Backend 配置 (result_expires) 处理。
# get_task_statistics: 使用 Flower 或 Celery API。
# wait_for_tasks: 使用 result.get() 或 result.collect()。
# task_decorator: 使用 @celery_app.task 的内置功能。