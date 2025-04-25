# bot_api_v1/app/tasks/celery_tasks.py
import time
import sys  # 确保导入sys模块
from bot_api_v1.app.core.config import settings
from datetime import datetime
from bot_api_v1.app.core.logger import logger
from celery.exceptions import Retry, MaxRetriesExceededError
from pydub import AudioSegment
from bot_api_v1.app.services.business.points_service import PointsService
from bot_api_v1.app.core.cache import get_task_result_from_cache, save_task_result_to_cache
from bot_api_v1.app.utils.media_extrat_format import Media_extract_format
from bot_api_v1.app.constants.media_info import MediaPlatform
from pathlib import Path  # 推荐使用 pathlib 处理路径
from bot_api_v1.app.tasks.celery_service_logic import prepare_media_for_transcription
from bot_api_v1.app.services.business.script_service_sync import ScriptService_Sync
from bot_api_v1.app.tasks.celery_app import celery_app

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

def get_task_b_result(origin_url:str): 
    return get_task_result_from_cache(origin_url)



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
def run_media_extraction_new(
    self,
    url: str,
    extract_text: bool,
    include_comments: bool,
    platform: str,
    user_id: str,
    trace_id: str,
    app_id: str,
    root_trace_key: str
):
    """
    Celery Task (Task A): V3 - 返回包含状态的字典。
    如果 extract_text=False 或无需转写，返回 {'status':'success', ...}。
    如果 extract_text=True 且需转写，触发 Task B，然后返回
    {'status':'processing', 'transcription_task_id': ..., 'basic_info': ...}。
    """
    task_id = self.request.id
    effective_trace_id = trace_id or task_id
    log_extra = {"request_id": effective_trace_id, "celery_task_id": task_id, "user_id": user_id, "app_id": app_id, "task_stage": "A", "root_trace_key": root_trace_key}
    logger.info_to_db(f"[Task A {task_id=}] V3 接收到任务, extract_text={extract_text}", extra=log_extra)

    try:
        task_b_result = get_task_b_result(url)
        if task_b_result:
            logger.info_to_db(f"[Task A {task_id}] 从缓存中捞到了url is {url}的Task B结果，那么直接返回", extra=log_extra)
            return task_b_result
    except Exception as e:
        logger.error(f"[Task A {task_id}] 试图从缓存中捞取url is {url}的Task B结果失败了,继续执行吧，错误信息: {e}", extra=log_extra)

    try:
        logger.info(f"[Task A {task_id=}] V3，没捞到缓存，需要提取文本，开始准备阶段...", extra=log_extra)
        prepare_result = prepare_media_for_transcription(platform, url,include_comments, user_id, trace_id, app_id,root_trace_key)

        if prepare_result.get("status") != "success":
            logger.error(f"[Task A {task_id=}] V3 准备阶段失败: {prepare_result.get('error')}", extra=log_extra)
            # 准备失败，直接返回失败字典，Task A 状态为 SUCCESS
            return prepare_result

        prepare_data = prepare_result.get("data", {})
        basic_info = prepare_data.get("basic_info")
        audio_path = prepare_data.get("audio_path")
        media_url_to_download = prepare_data.get("media_url_to_download")
        base_points = prepare_data.get("points_consumed", 0)
        # go_cache = prepare_data.get("go_cache", False)

        # if not go_cache and not audio_path: # 无需转写
        if not audio_path: # 无需转写
            logger.error(f"[Task A {task_id=}] V3 没有媒体audio_path is nul--无需转写", extra=log_extra)
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

        logger.info_to_db(f"[Task A {task_id=}] V3 准备阶段成功. 准备触发转写任务 (Task B)，需要{total_required}积分，用户积分充足{user_available_points}...", extra=log_extra)

        # 触发转写任务 (Task B)
        task_b_async_result = run_transcription_task.apply_async(
            args=(audio_path, media_url_to_download , user_id, effective_trace_id, app_id, basic_info, platform,url,audio_duration,root_trace_key),
            queue='transcription'
        )
        task_b_id = task_b_async_result.id
        logger.info_to_db(f"[Task A {task_id=}] V3 转写任务 ({task_b_id}) 已触发。", extra=log_extra)

        # !! 关键修改：返回包含处理中状态和信息的字典 !!
        processing_dict = {
            'status': 'processing', # 内部状态标记，告知 API 需查询 Task B
            'message': 'Awaiting transcription result',
            'transcription_task_id': task_b_id, # 存储 Task B 的 ID
            'basic_info': basic_info,         # 存储基础信息
            'base_points': base_points        # 存储基础积分
        }
        logger.info_to_db(f"[Task A {task_id=}] V3 返回 processing 字典。Task A 结束。", extra=log_extra)
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
    media_extract_format = Media_extract_format()
    basic_info = basic_info.get("data", {})  # 提取 video 字段
    info = {
        "platform": platform,
        "video_id": basic_info.get("id", ""),  # 使用 id 字段
        "original_url": url,
        "title": basic_info.get("desc", ""),
        "description": basic_info.get("desc", ""),
        "content": transcribed_text,
        "tags": media_extract_format._extract_tags_from_douyin(basic_info),
        
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
        
        "publish_time": media_extract_format._format_timestamp(basic_info.get("create_timestamp", 0)),
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
    media_extract_format = Media_extract_format()
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
        
        "publish_time": media_extract_format._format_timestamp(basic_info.get("create_time", 0)),
        "update_time": media_extract_format._format_timestamp(basic_info.get("last_update_time", 0))
    }

    return info


def create_bl_schema(
    basic_info: dict,
    transcribed_text: str):
    info = basic_info.copy()
    info["content"] = transcribed_text

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
    elif platform == MediaPlatform.BILIBILI:
        final_standard_data = create_bl_schema( basic_info, transcribed_text)
    else:
        logger.error(f"[Task B {task_id=}] 未知的平台: {platform}", extra=log_extra)
        final_standard_data = {}

    return final_standard_data


def get_audio_path(audio_path, log_extra):
    logger.info(f"转写前地址 audio_path is : {audio_path}", extra=log_extra)
    if audio_path:
        try:
            server_base_path_str = settings.SHARED_TEMP_DIR  # NFS 服务端共享的基础路径
            client_mount_point_str = settings.SHARED_MNT_DIR # 从设置读取客户端挂载点

            if not client_mount_point_str:
                logger.error("Client mount point (settings.SHARED_MNT_DIR) not configured!", extra=log_extra)
                # 根据你的错误处理逻辑，可能需要 return 或 raise exception
                # audio_path = None # 或者设为 None，让后续逻辑处理
            else:
                server_base_path = Path(server_base_path_str)
                full_server_path = Path(audio_path)
                client_mount_point = Path(client_mount_point_str)

                # 计算相对于 NFS 服务端基础路径的相对路径
                # 例如: full_server_path = /srv/nfs/shared/subdir/file.mp4
                #       server_base_path = /srv/nfs/shared
                #       relative_path will be "subdir/file.mp4"
                relative_path = full_server_path.relative_to(server_base_path)

                # 将相对路径拼接到客户端挂载点上
                # 例如: client_mount_point = /mnt/nfs_audio
                #       relative_path = subdir/file.mp4
                #       client_path will be /mnt/nfs_audio/subdir/file.mp4
                client_path = client_mount_point / relative_path

                # 将 Path 对象转换回字符串，以便后续可能需要字符串路径的代码使用
                audio_path = str(client_path)

                logger.info(f"转写后地址 audio_path is : {audio_path}", extra=log_extra)

                return audio_path
        except ValueError as e:
            # 如果 full_server_path 不是 server_base_path 的子路径，relative_to 会抛出 ValueError
            logger.error(f"Path translation error: {audio_path} is not relative to {server_base_path_str}. Error: {e}", extra=log_extra)
            audio_path = None # 标记路径无效
        except Exception as e:
            logger.error(f"Unexpected error during path translation for {audio_path}: {e}", extra=log_extra)
            audio_path = None # 标记路径无效
        logger.info(f"转写后地址 audio_path is : {audio_path}", extra=log_extra)
# --- 修改后的转写任务 (Task B) ---
@celery_app.task(
    name="tasks.run_transcription", # Task B
    bind=True,
    # ignore_result=True, # <<< 添加这个参数
    max_retries=1,
    default_retry_delay=60,
    acks_late=True,
    time_limit=600,
    soft_time_limit=240
)
def run_transcription_task(
    self,
    # 不再需要 original_task_id, basic_info, base_points
    audio_path: str,
    media_url_to_download: str,
    user_id: str,
    trace_id: str,
    app_id: str,
    basic_info: dict,
    platform: str,
    url: str,
    audio_duration : int,
    root_trace_key: str = None
    ):
    """
    Celery Task (Task B): 负责执行音频转写，并将转写结果作为自己的返回值。
    """
    task_id = self.request.id # Task B 自己的 ID
    effective_trace_id = trace_id
    log_extra = {"request_id": effective_trace_id, "celery_task_id": task_id, "user_id": user_id, "app_id": app_id, "task_stage": "B", "root_trace_key": root_trace_key}
        
    try:
        task_b_result = get_task_b_result(url)
        if task_b_result:
            logger.info_to_db(f"[Task B {task_id}] 从缓存中捞取url is {url}的结果返回", extra=log_extra)
            return task_b_result
    except Exception as e:
        logger.error(f"[Task B] 试图从缓存中捞取url is {url}的Task B结果失败了,继续执行吧，错误信息: {e}", extra=log_extra)
   
    logger.info(f"[Task B {task_id=}] 开始执行转写, audio_path={audio_path}", extra=log_extra)
    total_required,user_available_points = check_user_available_points_by_audio(audio_duration, user_id, task_id, log_extra)
    if user_available_points is None or user_available_points < total_required:
        msg = f"[Task B {task_id=}] V3 先检查积分信息，用户{user_id}积分不足，无法继续。需要{total_required}积分，用户仅有{user_available_points}积分"
        logger.error(msg, extra=log_extra)
        return {"status": "failed", "error": msg, "points_consumed": 0}

    logger.info(f"[Task B {task_id=}] V3 先检查积分部分，用户{user_id}需要{total_required}积分，积分充足{user_available_points}...", extra=log_extra)

    audio_path = get_audio_path(audio_path, log_extra)
    transcription_result_dict = {} # 用于存储最终结果
    try:
        script_service_sync = ScriptService_Sync()
        # 1. 执行转写
        transcription_result_dict = script_service_sync.transcribe_audio_sync(
            original_url=url,
            media_url_to_download=media_url_to_download,
            platform=platform,
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

                try:
                    save_task_result_to_cache(url,task_b_final_result)
                    logger.info_to_db(f"[Task B {task_id=}] 成功保存结果到缓存", extra=log_extra)
                except Exception as e:
                    logger.error(f"[Task B {task_id=}] 保存转写结果到缓存时出错: {e}", exc_info=True, extra=log_extra)

                return task_b_final_result
            except Exception as format_err:
                logger.error(f"[Task B {task_id=}] 格式化最终结果时出错: {format_err}", exc_info=True, extra=log_extra)
                error_message = f"任务成功但结果格式化失败: {format_err}"
                failure_result = {
                    "status": "failed",
                    "error": error_message,
                    "original_basic_info": basic_info,
                    "platform": platform,
                    "transcription_result": transcription_result_dict,
                    "exc_type": type(format_err).__name__,
                    "exc_message": str(format_err),
                    "exc_module": type(format_err).__module__
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



from bot_api_v1.app.services.log_service import LogService
@celery_app.task(
    name="tasks.save_log_to_db",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
    time_limit=30,
    soft_time_limit=20,
    queue='logging'  # 使用专门的日志队列
)
def save_log_to_db(
    self, 
    trace_key=None,
    method_name=None,
    source=None,
    app_id=None,
    user_uuid=None,
    user_nickname=None,
    entity_id=None,
    type=None,
    tollgate=None,
    level=None,
    para=None,
    header=None,
    body=None,
    description=None,
    memo=None,
    ip_address=None):
    """
    Celery任务：将日志保存到数据库

    参数与LogService.save_log保持一致
    """
    task_id = self.request.id
    start_time = datetime.now()
    
    try:
        print(f"[{start_time}] INFO: [Log Task {task_id}] 开始保存日志到数据库: {method_name}")
        
        # 使用同步方法直接保存日志
        from bot_api_v1.app.services.log_service import LogService
        result = LogService.save_log_sync(
            trace_key=trace_key,
            method_name=method_name,
            source=source,
            app_id=app_id,
            user_uuid=user_uuid,
            user_nickname=user_nickname,
            entity_id=entity_id,
            type=type,
            tollgate=tollgate,
            level=level,
            para=para,
            header=header,
            body=body,
            description=description,
            memo=memo,
            ip_address=ip_address
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        print(f"[{end_time}] INFO: [Log Task {task_id}] 日志保存成功，耗时: {duration:.3f}秒")
        return {"status": "success", "message": "日志保存成功", "duration": duration}
    except Exception as e:
        print(f"[{datetime.now()}] ERROR: [Log Task {task_id}] 保存日志失败: {str(e)}", file=sys.stderr)
        # 记录更详细的错误信息
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "trace_key": trace_key,
            "method_name": method_name
        }
        
        try:
            # 使用更详细的重试信息
            print(f"[{datetime.now()}] INFO: [Log Task {task_id}] 尝试重试，当前重试次数: {self.request.retries}")
            self.retry(exc=e, countdown=5 * (2 ** self.request.retries))  # 指数退避策略
        except Exception as retry_err:
            print(f"[{datetime.now()}] ERROR: [Log Task {task_id}] 重试保存日志失败: {str(retry_err)}", file=sys.stderr)
            return {
                "status": "failed", 
                "error": str(e), 
                "retry_error": str(retry_err),
                "error_details": error_details
            }




@celery_app.task(
    name="tasks.save_logs_batch",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
    time_limit=60, # 可以根据需要调整
    soft_time_limit=50,
    queue='logging'
)
def save_logs_batch(self, logs_data):
    """
    批量处理多条日志记录 (修改为使用同步方法)

    Args:
        logs_data: 包含多条日志记录的列表
    """
    task_id = self.request.id
    start_time = datetime.now()
    total_logs = len(logs_data)

    print(f"[{start_time}] INFO: [Batch Log Task {task_id}] 开始(同步)批量处理 {total_logs} 条日志")

    results = {
        "success": 0,
        "failed": 0,
        "errors": []
    }

    # 不再需要 asyncio 和 loop

    try:
        # 直接导入 LogService (或者在模块顶部导入)
        from bot_api_v1.app.services.log_service import LogService

        # 使用 for 循环逐条调用同步保存方法
        for i, log_data in enumerate(logs_data):
            try:
                # 调用同步方法
                save_successful = LogService.save_log_sync(**log_data)
                if save_successful:
                    results["success"] += 1
                else:
                    # 如果 save_log_sync 设计为失败时返回 False
                    results["failed"] += 1
                    results["errors"].append({
                        "index": i,
                        "error": "LogService.save_log_sync returned False or failed silently",
                        "log_data": log_data # 截断或选择性记录 log_data 以免过长
                    })
            except Exception as inner_e:
                # 捕获 save_log_sync 可能抛出的任何异常
                results["failed"] += 1
                results["errors"].append({
                    "index": i,
                    "error": f"Exception during save_log_sync: {str(inner_e)}",
                    "error_type": type(inner_e).__name__,
                    "log_data": log_data # 截断或选择性记录
                })
                # 打印内部错误，同样避免 logger
                print(f"[{datetime.now()}] ERROR: [Batch Log Task {task_id}] Error saving log at index {i}: {inner_e}", file=sys.stderr)


        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"[{end_time}] INFO: [Batch Log Task {task_id}] (同步)批量处理完成，"
              f"成功: {results['success']}/{total_logs}，"
              f"失败: {results['failed']}/{total_logs}，"
              f"耗时: {duration:.3f}秒")

        return {
            "status": "completed",
            "total": total_logs,
            "success": results["success"],
            "failed": results["failed"],
            "duration": duration,
            "errors": results["errors"] if results["failed"] > 0 else []
        }

    except Exception as e:
        # 处理任务级别的意外错误 (例如导入失败等)
        print(f"[{datetime.now()}] ERROR: [Batch Log Task {task_id}] 任务执行失败: {str(e)}", file=sys.stderr)
        try:
            # 这里仍然可以重试整个批次，但可能导致已成功的日志被重复处理
            # 或者选择不重试，接受这批日志处理失败
            # self.retry(exc=e, countdown=10 * (2 ** self.request.retries))
            # return a failed status without retry:
             return {
                 "status": "failed",
                 "error": f"Outer task exception: {str(e)}",
                 "total": total_logs,
                 "success": results["success"], # Report any successes before the outer exception
                 "failed": total_logs - results["success"], # Assume the rest failed
             }
        except Exception as retry_err: # Catch potential retry errors
            return {
                "status": "failed",
                "error": str(e),
                "retry_error": str(retry_err)
            }
    # finally: loop.close() # 不再需要这一行

# @celery_app.task(
#     name="tasks.save_logs_batch",
#     bind=True,
#     max_retries=3,
#     default_retry_delay=10,
#     acks_late=True,
#     time_limit=60,
#     soft_time_limit=50,
#     queue='logging'
# )
# def save_logs_batch(self, logs_data):
#     """
#     批量处理多条日志记录
    
#     Args:
#         logs_data: 包含多条日志记录的列表
#     """
#     task_id = self.request.id
#     start_time = datetime.now()
#     total_logs = len(logs_data)
    
#     print(f"[{start_time}] INFO: [Batch Log Task {task_id}] 开始批量处理 {total_logs} 条日志")
    
#     results = {
#         "success": 0,
#         "failed": 0,
#         "errors": []
#     }
    
#     import asyncio
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
    
#     try:
#         # 创建所有日志保存任务的协程
#         async def save_all_logs():
#             tasks = []
#             for log_data in logs_data:
#                 tasks.append(LogService.save_log(**log_data))
            
#             # 并发执行所有任务
#             results_list = await asyncio.gather(*tasks, return_exceptions=True)
#             return results_list
        
#         # 执行批量保存
#         results_list = loop.run_until_complete(save_all_logs())
        
#         # 处理结果
#         for i, result in enumerate(results_list):
#             if isinstance(result, Exception):
#                 results["failed"] += 1
#                 results["errors"].append({
#                     "index": i,
#                     "error": str(result),
#                     "log_data": logs_data[i]
#                 })
#             else:
#                 results["success"] += 1
        
#         end_time = datetime.now()
#         duration = (end_time - start_time).total_seconds()
        
#         print(f"[{end_time}] INFO: [Batch Log Task {task_id}] 批量处理完成，"
#               f"成功: {results['success']}/{total_logs}，"
#               f"失败: {results['failed']}/{total_logs}，"
#               f"耗时: {duration:.3f}秒")
        
#         return {
#             "status": "completed",
#             "total": total_logs,
#             "success": results["success"],
#             "failed": results["failed"],
#             "duration": duration,
#             "errors": results["errors"] if results["failed"] > 0 else []
#         }
    
#     except Exception as e:
#         print(f"[{datetime.now()}] ERROR: [Batch Log Task {task_id}] 批量处理失败: {str(e)}", file=sys.stderr)
#         try:
#             self.retry(exc=e, countdown=10 * (2 ** self.request.retries))
#         except Exception as retry_err:
#             return {
#                 "status": "failed",
#                 "error": str(e),
#                 "retry_error": str(retry_err)
#             }
#     finally:
#         loop.close()  # 确保事件循环被关闭