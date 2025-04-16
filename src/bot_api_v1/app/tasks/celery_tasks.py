# bot_api_v1/app/tasks/celery_tasks.py
import time
from bot_api_v1.app.core.logger import logger
import asyncio
from celery.exceptions import Retry, MaxRetriesExceededError
from celery.result import AsyncResult # 保留导入，虽然在此文件中可能不用了
from bot_api_v1.app.services.business.media_service import MediaService,MediaPlatform
from pydub import AudioSegment
from bot_api_v1.app.services.business.points_service import PointsService

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



def check_user_available_points_by_audio(
    audio_duration: int,
    user_id: str,
    task_id: str,
    log_extra: dict
):
    duration_seconds = int(audio_duration)
    duration_points = (duration_seconds // 60) * 10
    if duration_seconds % 60 > 0 or duration_seconds == 0:
            duration_points += 10
    total_required = duration_points

    # 读取db，获取用户积分
    points_service = PointsService()
    user_available_points = points_service.get_user_points_sync(user_id)
    
    return total_required,user_available_points


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
        logger.info(f"[Task A {task_id=}] V3 需要提取文本，开始准备阶段...", extra=log_extra)
        prepare_result = prepare_media_for_transcription(platform, url,include_comments, user_id, trace_id, app_id)

        if prepare_result.get("status") != "success":
            logger.error(f"[Task A {task_id=}] V3 准备阶段失败: {prepare_result.get('error')}", extra=log_extra)
            # 准备失败，直接返回失败字典，Task A 状态为 SUCCESS
            return prepare_result

        prepare_data = prepare_result.get("data", {})
        basic_info = prepare_data.get("basic_info")
        audio_path = prepare_data.get("audio_path")
        base_points = prepare_data.get("points_consumed", 0)

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

        audio = AudioSegment.from_file(audio_path)
        audio_duration = len(audio) / 1000
        total_required,user_available_points = check_user_available_points_by_audio(audio_duration, user_id, task_id, log_extra)
        
        if user_available_points is None or user_available_points < total_required:
            msg = f"[Task A {task_id=}] V3 用户{user_id}积分不足，无法继续。需要{total_required}积分，用户仅有{user_available_points}积分"
            logger.error(msg, extra=log_extra)
            return {"status": "failed", "error": msg, "points_consumed": 0}

        logger.info(f"[Task A {task_id=}] V3 准备阶段成功. 准备触发转写任务 (Task B)，需要{total_required}积分，用户积分充足{user_available_points}...", extra=log_extra)

        # 触发转写任务 (Task B)
        task_b_async_result = run_transcription_task.apply_async(
            args=(audio_path, user_id, effective_trace_id, app_id, basic_info, platform,url,audio_duration),
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
        
    except Exception as e:
        # ... 处理异常，最终应该 return 一个失败字典 ...
        logger.error(f"[Task A {task_id=}] V3 执行时发生顶层错误: {e}", exc_info=True, extra=log_extra)
        # 注意：如果这里抛出未捕获的异常，Task A 状态会是 FAILURE
        # 但如果捕获了并返回字典，状态是 SUCCESS，需要在字典中标明失败
        return {"status": "failed", "error": f"Task A 意外失败: {str(e)}", "points_consumed": 0}


def create_douyin_schema(
    platform: str,
    basic_info: dict,
    url: str,
    transcribed_text: str,
    audio_duration: int
):
    _media_service = MediaService()
    basic_info = basic_info.get("data", {})  # 提取 video 字段
    info = {
        "platform": platform,
        "video_id": basic_info.get("id", ""),  # 使用 id 字段
        "original_url": url,
        "title": basic_info.get("desc", ""),
        "description": basic_info.get("desc", ""),
        "content": transcribed_text,
        "tags": _media_service._extract_tags_from_douyin(basic_info),
        
        "author": {
            "id": basic_info.get("uid", ""),  # 直接从顶层获取
            "sec_uid": basic_info.get("sec_uid", ""),  # 直接从顶层获取
            "nickname": basic_info.get("nickname", ""),  # 直接从顶层获取
            "avatar": "",  # 视频信息中可能没有头像URL
            "signature": basic_info.get("signature", ""),  # 直接从顶层获取
            "verified": False,  # 默认为False
            "follower_count": 0,  # 视频信息中可能没有粉丝数
            "following_count": 0,  # 视频信息中可能没有关注数
            "region": ""  # 视频信息中可能没有地区信息
        },
        
        "statistics": {
            "like_count": basic_info.get("digg_count", 0),  # 直接从顶层获取
            "comment_count": basic_info.get("comment_count", 0),  # 直接从顶层获取
            "share_count": basic_info.get("share_count", 0),  # 直接从顶层获取
            "collect_count": basic_info.get("collect_count", 0),  # 直接从顶层获取
            "play_count": basic_info.get("play_count", 0)  # 直接从顶层获取
        },
        
        "media": {
            "cover_url": basic_info.get("origin_cover", ""),  # 使用原始封面
            "video_url": basic_info.get("downloads", ""),  # 使用下载链接
            "duration": round(audio_duration) if audio_duration is not None else 0, # <<< 使用 round() 转换
            "width": basic_info.get("width", 0),  # 直接从顶层获取
            "height": basic_info.get("height", 0),  # 直接从顶层获取
            "quality": "normal"
        },
        
        "publish_time": _media_service._format_timestamp(basic_info.get("create_timestamp", 0)),
        "update_time": None
    }

    return info


def create_xhs_schema(
    platform: str,
    basic_info: dict,
    url: str,
    transcribed_text: str,
    audio_duration: int
):
    media_service = MediaService()
    info = {
        "platform": platform,
        "video_id": basic_info.get("note_id", ""),
        "original_url": url,
        "title": basic_info.get("title", ""),
        "description": basic_info.get("desc", ""),
        "content": transcribed_text,
        "tags": basic_info.get("tags", []),
        
        "author": {
            "id": basic_info.get("author", {}).get("id", ""),
            "sec_uid": basic_info.get("author", {}).get("user_id", ""),
            "nickname": basic_info.get("author", {}).get("nickname", ""),
            "avatar": basic_info.get("author", {}).get("avatar", ""),
            "signature": basic_info.get("author", {}).get("signature", ""),
            "verified": basic_info.get("author", {}).get("verified", False),
            "follower_count": basic_info.get("author", {}).get("follower_count", 0),
            "following_count": basic_info.get("author", {}).get("following_count", 0),
            "region": basic_info.get("author", {}).get("location", "")
        },
        
        "statistics": {
            "like_count": basic_info.get("statistics", {}).get("like_count", 0),
            "comment_count": basic_info.get("statistics", {}).get("comment_count", 0),
            "share_count": basic_info.get("statistics", {}).get("share_count", 0),
            "collect_count": basic_info.get("statistics", {}).get("collected_count", 0),
            "play_count": basic_info.get("statistics", {}).get("view_count", 0)
        },
        
        "media": {
            "cover_url": basic_info.get("media", {}).get("cover_url", ""),
            "video_url": basic_info.get("media", {}).get("video_url", ""),
            "duration": round(audio_duration) if audio_duration is not None else 0, # <<< 使用 round() 转换
            "width": basic_info.get("media", {}).get("width", 0),
            "height": basic_info.get("media", {}).get("height", 0),
            "quality": "normal"
        },
        
        "publish_time": media_service._format_timestamp(basic_info.get("create_time", 0)),
        "update_time": media_service._format_timestamp(basic_info.get("last_update_time", 0))
    }

    return info

def create_schema(
    task_id: str,
    basic_info: dict,
    platform: str,
    url: str,
    transcribed_text: str,
    log_extra: dict,
    audio_duration: int
):
    if platform == MediaPlatform.DOUYIN:
        # 转换为统一结构
        final_standard_data = create_douyin_schema(platform, basic_info, url, transcribed_text,audio_duration)
    elif platform == MediaPlatform.XIAOHONGSHU:
        final_standard_data = create_xhs_schema(platform, basic_info, url, transcribed_text,audio_duration)
    else:
        logger.error(f"[Task B {task_id=}] 未知的平台: {platform}", extra=log_extra)
        final_standard_data = {}

    return final_standard_data

# --- 修改后的转写任务 (Task B) ---
@celery_app.task(
    name="tasks.run_transcription", # Task B
    bind=True,
    # ignore_result=True, # <<< 添加这个参数
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
                           app_id: str,
                           basic_info: dict,
                           platform: str,
                           url: str,
                           audio_duration : int,
                           ):
    """
    Celery Task (Task B): 负责执行音频转写，并将转写结果作为自己的返回值。
    """
    task_id = self.request.id # Task B 自己的 ID
    effective_trace_id = trace_id
    log_extra = {"request_id": effective_trace_id, "celery_task_id": task_id, "user_id": user_id, "app_id": app_id, "task_stage": "B"}
    logger.info(f"[Task B {task_id=}] 开始执行转写, audio_path={audio_path}", extra=log_extra)

    total_required,user_available_points = check_user_available_points_by_audio(audio_duration, user_id, task_id, log_extra)
    if user_available_points is None or user_available_points < total_required:
        msg = f"[Task B {task_id=}] V3 先检查积分信息，用户{user_id}积分不足，无法继续。需要{total_required}积分，用户仅有{user_available_points}积分"
        logger.error(msg, extra=log_extra)
        return {"status": "failed", "error": msg, "points_consumed": 0}

    logger.info(f"[Task B {task_id=}] V3 先检查积分部分，用户{user_id}需要{total_required}积分，积分充足{user_available_points}...", extra=log_extra)

    transcription_result_dict = {} # 用于存储最终结果
    try:
        script_service = ScriptService()
        # 1. 执行转写
        transcription_result_dict = script_service.transcribe_audio_sync(
            audio_path=audio_path,
            trace_id=effective_trace_id
        )

        # 2. 处理转写结果
        if transcription_result_dict.get("status") == "success":
            logger.info(f"[Task B {task_id=}] 转写成功", extra=log_extra)
            # 2.2 调用格式化函数
            try:
                transcribed_text = transcription_result_dict.get("text")
                final_standard_data = create_schema(
                    task_id=task_id,
                    basic_info=basic_info,
                    platform=platform,
                    url=url,
                    transcribed_text=transcribed_text,
                    log_extra=log_extra,
                    audio_duration=audio_duration
                )

                # 2.4 构建 Task B 的最终成功返回值
                task_b_final_result = {
                    "status": "success",
                    "message": "Extraction, transcription, and formatting successful.",
                    "data": final_standard_data, # 包含已格式化的数据
                    "points_consumed": total_required    # 包含从 basic_info 提取的积分
                }
                logger.info(f"[Task B {task_id=}] 返回包含最终格式数据的成功结果，task_b_final_result is {task_b_final_result}。", extra=log_extra)
                return task_b_final_result

                # logger.info(f"[Task B {task_id=}] 返回简化的测试结果...")
                # simplified_data = {
                #     "video_id": final_standard_data.get("video_id", "test_id_placeholder"),
                #     "platform": final_standard_data.get("platform", "unknown")
                #     # 只包含极少数确定安全的字段
                # }
                # test_result = {
                #     "status": "success",
                #     "message": "Simplified test return",
                #     "data": simplified_data,
                #     "points_consumed": total_required # points 应该是数字，是安全的
                # }
                # return test_result

            except Exception :
                 logger.error(f"[Task B {task_id=}] 格式化最终结果时出错: {format_err}", exc_info=True, extra=log_extra)
                 # 格式化失败，也算 Task B 失败
                 error_message = f"任务成功但结果格式化失败: {format_err}"
                 failure_result = {
                    "status": "failed",
                    "error": error_message,
                    "original_basic_info": basic_info, # 返回原始信息
                    "platform": platform,
                    "transcription_result": transcription_result_dict # 返回原始转写结果
                 }
                 self.update_state(state='FAILURE', meta=failure_result)
                 return failure_result
        else:
            error_message = transcription_result_dict.get("error", "转写失败，未知原因")
            logger.error(f"[Task B {task_id=}] 转写失败: {error_message}", extra=log_extra)
            failure_result = {
                "status": "failed",
                "error": error_message,
                "exc_type": "TranscriptionError",
                "exc_message": error_message,
                "points_consumed": 0
            }
            self.update_state(state='FAILURE', meta=failure_result)
            return failure_result  # 返回失败结果而不是 None

    except Exception as e:
        error_dict = {
            "status": "failed",
            "error": f"转写时发生意外错误: {str(e)}",
            "points_consumed": 0,
            "exc_type": type(e).__name__,
            "exc_message": str(e)
        }
        logger.error(f"[Task B {task_id=}] 转写时发生顶层错误: {e}", exc_info=True, extra=log_extra)
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            self.update_state(state='FAILURE', meta=error_dict)
            return error_dict  # 返回错误信息而不是 None
        except Exception as retry_error:
            error_dict.update({
                "error": f"重试失败: {str(retry_error)}",
                "exc_type": type(retry_error).__name__,
                "exc_message": str(retry_error)
            })
            self.update_state(state='FAILURE', meta=error_dict)
            return error_dict  # 返回错误信息而不是 None
