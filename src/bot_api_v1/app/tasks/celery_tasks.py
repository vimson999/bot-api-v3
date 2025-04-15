# bot_api_v1/app/tasks/celery_tasks.py
import time
from bot_api_v1.app.core.logger import logger
import asyncio
from celery.exceptions import Retry, MaxRetriesExceededError
from celery.result import AsyncResult # 保留导入，虽然在此文件中可能不用了

# 导入 celery_app 实例
try:
    from .celery_app import celery_app
except ImportError:
    logger.error("无法导入 celery_app...", exc_info=True)
    raise

# !! 导入重构后的服务逻辑函数 !!
try:
    from bot_api_v1.app.tasks.celery_service_logic import (
        fetch_basic_media_info,
        prepare_media_for_transcription,
    )
    from bot_api_v1.app.services.business.script_service import ScriptService, AudioTranscriptionError
except ImportError:
     logger.error("无法导入重构后的 celery_service_logic 函数", exc_info=True)
     # 定义假的函数以便加载
     def fetch_basic_media_info(*args, **kwargs): return {"status":"failed", "error":"Logic not loaded"}
     def prepare_media_for_transcription(*args, **kwargs): return {"status":"failed", "error":"Logic not loaded"}
     class ScriptService:
         def transcribe_audio_sync(self, *args, **kwargs): return {"status":"failed", "error":"Service not loaded"}


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






# --- 修改后的媒体提取任务 (Task A) ---
@celery_app.task(
    name="tasks.run_media_extraction_new", # Task A
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    acks_late=True,
    time_limit=300,
    soft_time_limit=240
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
    Celery Task (Task A): V3 - 返回包含状态的字典。
    如果 extract_text=False 或无需转写，返回 {'status':'success', ...}。
    如果 extract_text=True 且需转写，触发 Task B，然后返回
    {'status':'processing', 'transcription_task_id': ..., 'basic_info': ...}。
    """
    task_id = self.request.id
    effective_trace_id = trace_id or task_id
    log_extra = {"request_id": effective_trace_id, "celery_task_id": task_id, "user_id": user_id, "app_id": app_id, "task_stage": "A"}
    logger.info(f"[Task A {task_id=}] V3 接收到任务, extract_text={extract_text}", extra=log_extra)

    try:
        if not extract_text:
            # --- 情况 1: 只需基础信息 ---
            logger.info(f"[Task A {task_id=}] V3 只提取基础信息", extra=log_extra)
            result_dict = fetch_basic_media_info(platform, url, include_comments, user_id, trace_id, app_id)
            return result_dict # 返回 {'status': 'success', 'data': ...} 或失败字典
        else:
            # --- 情况 2: 需要提取文本 ---
            logger.info(f"[Task A {task_id=}] V3 需要提取文本，开始准备阶段...", extra=log_extra)
            prepare_result = prepare_media_for_transcription(platform, url,include_comments, user_id, trace_id, app_id)

            if prepare_result.get("status") != "success":
                 logger.error(f"[Task A {task_id=}] V3 准备阶段失败: {prepare_result.get('error')}", extra=log_extra)
                 # 准备失败，直接返回失败字典，Task A 状态为 SUCCESS
                 return prepare_result

            prepare_data = prepare_result.get("data", {})
            basic_info = prepare_data.get("basic_info")
            audio_path = prepare_data.get("audio_path")
            base_points = prepare_result.get("points_consumed", 0)

            if not audio_path: # 无需转写
                logger.info(f"[Task A {task_id=}] V3 媒体无需转写", extra=log_extra)
                return {
                    "status": "success", # 直接成功
                    "data": basic_info,
                    "points_consumed": base_points,
                    "message": prepare_result.get("message", "提取成功，无需转写")
                }

            if not basic_info:
                 logger.error(f"[Task A {task_id=}] V3 准备阶段成功但 basic_info 丢失", extra=log_extra)
                 return {"status": "failed", "error": "内部错误：准备阶段基础信息丢失", "points_consumed": 0}

            logger.info(f"[Task A {task_id=}] V3 准备阶段成功. 准备触发转写任务 (Task B)...", extra=log_extra)

            # 触发转写任务 (Task B)
            task_b_async_result = run_transcription_task.apply_async(
                args=(audio_path, user_id, effective_trace_id, app_id),
                queue='transcription'
            )
            task_b_id = task_b_async_result.id
            logger.info(f"[Task A {task_id=}] V3 转写任务 ({task_b_id}) 已触发。", extra=log_extra)

            # !! 关键修改：返回包含处理中状态和信息的字典 !!
            processing_dict = {
                'status': 'processing', # 内部状态标记，告知 API 需查询 Task B
                'message': 'Awaiting transcription result',
                'transcription_task_id': task_b_id, # 存储 Task B 的 ID
                'basic_info': basic_info,         # 存储基础信息
                'base_points': base_points        # 存储基础积分
            }
            logger.info(f"[Task A {task_id=}] V3 返回 processing 字典。Task A 结束。", extra=log_extra)
            return processing_dict # Task A 状态为 SUCCESS, result 为此字典

    # ... (异常处理部分) ...
    except Exception as e:
        # ... 处理异常，最终应该 return 一个失败字典 ...
        logger.error(f"[Task A {task_id=}] V3 执行时发生顶层错误: {e}", exc_info=True, extra=log_extra)
        # 注意：如果这里抛出未捕获的异常，Task A 状态会是 FAILURE
        # 但如果捕获了并返回字典，状态是 SUCCESS，需要在字典中标明失败
        return {"status": "failed", "error": f"Task A 意外失败: {str(e)}", "points_consumed": 0}


# --- 修改后的转写任务 (Task B) ---
@celery_app.task(
    name="tasks.run_transcription", # Task B
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    acks_late=True,
    time_limit=300,
    soft_time_limit=240
)
def run_transcription_task(self,
                           # 不再需要 original_task_id, basic_info, base_points
                           audio_path: str,
                           user_id: str,
                           trace_id: str,
                           app_id: str
                           ):
    """
    Celery Task (Task B): 负责执行音频转写，并将转写结果作为自己的返回值。
    """
    task_id = self.request.id # Task B 自己的 ID
    effective_trace_id = trace_id
    log_extra = {"request_id": effective_trace_id, "celery_task_id": task_id, "user_id": user_id, "app_id": app_id, "task_stage": "B"}
    logger.info(f"[Task B {task_id=}] 开始执行转写, audio_path={audio_path}", extra=log_extra)

    script_service = ScriptService()
    transcription_result_dict = {} # 用于存储最终结果

    try:
        # 1. 执行转写
        transcription_result_dict = script_service.transcribe_audio_sync(
            audio_path=audio_path,
            trace_id=effective_trace_id
        )

        # 2. 处理转写结果
        if transcription_result_dict.get("status") == "success":
            logger.info(f"[Task B {task_id=}] 转写成功", extra=log_extra)
            # Task B 成功完成，直接返回包含转写结果的字典
            # Celery 会将此字典存入 Task B 的 result 字段，并将 Task B 状态设为 SUCCESS
            return transcription_result_dict
        else:
            error_message = transcription_result_dict.get("error", "转写失败，未知原因")
            logger.error(f"[Task B {task_id=}] 转写失败: {error_message}", extra=log_extra)
            # Task B 失败，更新自身状态为 FAILURE，并将错误信息存入 meta
            self.update_state(state='FAILURE', meta=transcription_result_dict)
            # 返回 None 或 错误字典 都可以，状态优先
            return None

    # ... (异常处理：捕获转写中的错误) ...
    except Exception as e:
        error_dict = {"status": "failed", "error": f"转写时发生意外错误: {str(e)}", "points_consumed": 0}
        logger.error(f"[Task B {task_id=}] 转写时发生顶层错误: {e}", exc_info=True, extra=log_extra)
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            self.update_state(state='FAILURE', meta=error_dict) # 最终失败
        except Exception: # 重试本身失败
             self.update_state(state='FAILURE', meta=error_dict)
        return None # 返回 None
