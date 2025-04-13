# bot_api_v1/app/tasks/celery_tasks.py
import time
from bot_api_v1.app.core.logger import logger
import asyncio # 用于 run_async_in_sync (如果 celery_service_logic 需要)

# 导入 celery_app 实例
try:
    from .celery_app import celery_app
except ImportError:
    logger.error("无法导入 celery_app，请检查 celery_tasks.py 相对于 celery_app.py 的路径和你的 Python Path 设置。")
    raise

# 导入新的同步业务逻辑函数
try:
    from .celery_service_logic import execute_media_extraction_sync
except ImportError:
     logger.error("无法导入 celery_service_logic，请检查路径。")
     # 定义一个假的函数，以便至少能加载
     def execute_media_extraction_sync(*args, **kwargs):
         logger.error("execute_media_extraction_sync 未正确导入!")
         return {"status": "failed", "error": "Celery 服务逻辑未加载", "points_consumed": 0}


# --- 保留之前的示例任务 (可选) ---
@celery_app.task(name="tasks.add")
def add(x, y):
    result = x + y
    logger.info(f"[Celery Task 'add'] 执行: {x} + {y} = {result}")
    return result

@celery_app.task(name="tasks.long_running_task")
def long_running_task(duration=5):
    logger.info(f"[Celery Task 'long_running_task'] 开始执行，将持续 {duration} 秒...")
    time.sleep(duration)
    result_message = f"任务在 {duration} 秒后完成。"
    logger.info(f"[Celery Task 'long_running_task'] {result_message}")
    return result_message

@celery_app.task(name="tasks.print_message")
def print_message(message):
    logger.info(f"[Celery Task 'print_message'] 收到消息: '{message}'")
    processed_msg = f"消息 '{message}' 已处理。"
    return processed_msg

# --- 新的媒体提取任务 ---
@celery_app.task(
    name="tasks.run_media_extraction_new", # 新任务名
    bind=True,
    max_retries=1,
    default_retry_delay=60, # 1分钟后重试
    acks_late=True, # 对于长任务，建议开启，任务执行后才确认消息
    time_limit=1800, # 示例：硬超时 30 分钟
    soft_time_limit=1740 # 示例：软超时 29 分钟
)
def run_media_extraction_new(self,
                             url: str,
                             extract_text: bool,
                             include_comments: bool,
                             platform: str,
                             user_id: str,
                             trace_id: str,
                             app_id: str
                            ):
    """
    Celery Task 包装器：调用新的同步媒体提取和转写逻辑。
    """
    task_id = self.request.id
    # 如果 API 端没传递 trace_id，可以用 Celery 的 task_id 代替
    effective_trace_id = trace_id or task_id
    log_extra = {"request_id": effective_trace_id, "celery_task_id": task_id, "user_id": user_id, "app_id": app_id}
    logger.info(f"[Celery Task {task_id=}] 接收到任务, 调用同步逻辑. trace_id={effective_trace_id}", extra=log_extra)

    try:
        # 调用新的同步业务逻辑函数
        result_dict = execute_media_extraction_sync(
            url=url,
            extract_text=extract_text,
            include_comments=include_comments,
            platform=platform,
            user_id=user_id,
            trace_id=effective_trace_id,
            app_id=app_id
        )
        logger.info_to_db(f"[Celery Task {task_id=}] 同步逻辑执行完成. Result status: {result_dict.get('status')}", extra=log_extra)
        # 直接返回业务逻辑函数的字典结果
        return result_dict

    except Exception as e:
        # 捕获同步逻辑函数本身可能抛出的、未在内部处理的异常
        logger.error(f"[Celery Task {task_id=}] 调用同步逻辑时发生顶层错误: {e}", exc_info=True, extra=log_extra)
        try:
            # 尝试重试
            countdown = int(self.default_retry_delay * (2 ** self.request.retries))
            logger.info(f"[Celery Task {task_id=}] 发生顶层错误，将在 {countdown} 秒后重试 (第 {self.request.retries + 1} 次)", extra=log_extra)
            # 注意: retry 会抛出异常来中断当前执行并重新排队
            self.retry(exc=e, countdown=countdown)
            # retry 抛出异常后，下面的代码不会执行，所以不需要显式 return
        except self.MaxRetriesExceededError:
             logger.error(f"[Celery Task {task_id=}] 重试次数耗尽，顶层错误导致最终失败", extra=log_extra)
             # 返回最终失败信息
             return {"status": "failed", "error": f"处理失败，重试次数耗尽 ({effective_trace_id})", "exception": str(e), "points_consumed": 0}
        except Exception as retry_exc:
             # 处理 retry 本身的异常 (例如连接 Broker 失败)
             logger.error(f"[Celery Task {task_id=}] 尝试重试顶层错误时失败: {retry_exc}", exc_info=True, extra=log_extra)
             # 这种情况下任务也算失败了
             return {"status": "failed", "error": f"处理失败且无法重试 ({effective_trace_id})", "exception": str(e), "points_consumed": 0}