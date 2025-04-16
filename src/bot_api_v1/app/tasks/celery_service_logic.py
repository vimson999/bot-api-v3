from sqlalchemy import false
from bot_api_v1.app.services.business.media_service import MediaPlatform, MediaError
from bot_api_v1.app.services.business.xhs_service import XHSService, XHSError , handle_note_info 
from bot_api_v1.app.services.business.script_service import ScriptService, AudioDownloadError, AudioTranscriptionError
from bot_api_v1.app.constants.media_info import MediaType

from bot_api_v1.app.core.logger import logger
import time
import os
import asyncio # 用于 run_async_in_sync (如果 celery_service_logic 需要)

# !! 导入新的同步缓存装饰器 !!
from bot_api_v1.app.core.cache import cache_result_sync 
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.tasks.celery_tiktok_service import CeleryTikTokService, TikTokError, InitializationError,VideoFetchError # 新的 TikTok 服务


SPIDER_XHS_LOADED = True 
# 这个函数现在是分发器，并应用缓存
@cache_result_sync(
    expire_seconds=settings.CACHE_EXPIRATION or 1800, 
    prefix="celery_media_extract_sync", # 统一前缀或分开？暂时统一
    skip_args=['trace_id', 'user_id', 'app_id'] 
)
def execute_media_extraction_sync(
    url: str,
    extract_text: bool,
    include_comments: bool, # 这个参数只对 XHS relevant?
    platform: str,
    user_id: str, 
    trace_id: str, 
    app_id: str   
) -> dict:
    """
    [同步执行] 分发器：根据平台调用对应的 Service 的同步方法。
    应用缓存装饰器。
    """
    log_extra = {"request_id": trace_id, "user_id": user_id, "app_id": app_id}
    logger.info(f"[Sync Logic Dispatcher {trace_id=}] 分发任务: platform={platform}, url={url}", extra=log_extra)

    try:
        if platform == MediaPlatform.XIAOHONGSHU:
            # --- 调用原 XHSService 的同步方法 ---
            logger.debug("[Sync Logic Dispatcher] Using XHSService.get_note_info_sync_for_celery", extra=log_extra)
            xhs_service = XHSService() 
            # !! 假设 XHSService 已有此同步方法 !!
            result_dict = xhs_service.get_note_info_sync_for_celery( 
                url=url, 
                extract_text=extract_text, 
                user_id_for_points=user_id, 
                trace_id=trace_id
            )
        elif platform == MediaPlatform.DOUYIN:
            # --- 调用新的 CeleryTikTokService 的同步方法 ---
            logger.debug("[Sync Logic Dispatcher] Using CeleryTikTokService.get_video_info_sync", extra=log_extra)
            # 注意：新 Service 在 __init__ 中初始化，方法结束后在 finally 中清理
            celery_tiktok_service = CeleryTikTokService() 
            result_dict = celery_tiktok_service.get_video_info_sync(
                url=url, 
                extract_text=extract_text,
                user_id_for_points=user_id,
                trace_id=trace_id
            )
        else:
            raise MediaError(f"不支持的媒体平台: {platform}")

        logger.info(f"[Sync Logic Dispatcher {trace_id=}] 平台逻辑执行完成. Status: {result_dict.get('status')}", extra=log_extra)
        return result_dict

    # 捕获所有可能的服务层异常
    except (XHSError, TikTokError, MediaError, InitializationError) as e: 
        error_msg = f"处理失败 ({type(e).__name__}): {str(e)}"
        logger.error(f"[Sync Logic Dispatcher {trace_id=}] {error_msg}", extra=log_extra, exc_info=False)
        return {"status": "failed", "error": error_msg, "points_consumed": 0}
    except Exception as e: 
        error_msg = f"分发或执行时发生意外错误: {str(e)}"
        logger.error(f"[Sync Logic Dispatcher {trace_id=}] {error_msg}", exc_info=True, extra=log_extra)
        return {"status": "failed", "error": f"发生内部错误 ({trace_id})", "exception": str(e), "points_consumed": 0}







# --- 1. 获取基础媒体信息 (适用于 Task A - extract_text=False) ---
@cache_result_sync(
    expire_seconds=settings.CACHE_EXPIRATION or 1800,
    prefix="fetch_basic_media",
    skip_args=['trace_id', 'user_id', 'app_id'] # 缓存不应依赖这些请求上下文变量
)
def fetch_basic_media_info(
    platform: str,
    url: str,
    include_comments: bool, # 注意：可能只对特定平台有意义
    user_id: str,
    trace_id: str,
    app_id: str
) -> dict:
    """
    [同步执行] 只获取媒体的基础信息 (元数据, URL等), 不下载文件, 不转写。
    应用缓存。
    """
    log_extra = {"request_id": trace_id, "user_id": user_id, "app_id": app_id, "logic_step": "fetch_basic"}
    logger.info(f"[Fetch Basic {trace_id=}] 开始获取基础信息: platform={platform}, url={url}", extra=log_extra)

    base_cost = 10 # 假设基础信息固定成本
    media_data = None

    try:
        if platform == MediaPlatform.XIAOHONGSHU:
            if not SPIDER_XHS_LOADED: raise XHSError("小红书模块未加载")
            xhs_service = XHSService() # 实例化服务
            # 调用 XHS API 获取原始数据 (假设这是阻塞的)
            logger.debug("[Fetch Basic XHS] 调用 xhs_apis.get_note_info...", extra=log_extra)
            success, msg, note_data_raw = xhs_service.xhs_apis.get_note_info(url, xhs_service.cookies_str)
            if not success or not note_data_raw:
                raise XHSError(f"获取小红书笔记API失败: {msg}")
            # 解析和转换格式 (同步)
            try:
                # 添加原始 URL 到原始数据中，方便后续处理
                if 'data' in note_data_raw and 'items' in note_data_raw['data'] and note_data_raw['data']['items']:
                     note_data_raw['data']['items'][0]['url'] = url
                     note_info_parsed = handle_note_info(note_data_raw['data']['items'][0])
                     media_data = xhs_service._convert_note_to_standard_format(note_info_parsed)
                else:
                    raise XHSError("API 返回数据结构不符合预期")
            except Exception as e:
                 logger.error(f"[Fetch Basic XHS] 解析笔记数据失败: {e}", exc_info=True, extra=log_extra)
                 raise XHSError(f"解析笔记数据失败: {str(e)}")

        elif platform == MediaPlatform.DOUYIN:
            tiktok_service = None
            try:
                tiktok_service = CeleryTikTokService() # 实例化服务 (包含初始化和清理)
                extract_text=True
                # 调用内部封装好的同步获取基础信息的方法
                # 这个方法内部处理了在线程池中运行异步代码的逻辑
                media_data = tiktok_service.get_basic_video_info_sync_internal(
                    url=url,
                    extract_text=extract_text,
                    user_id_for_points=user_id,
                    trace_id=trace_id
                )
                if media_data is None: # 检查返回值
                     raise TikTokError("未能获取抖音基础信息 (内部方法返回 None)")
            finally:
                 if tiktok_service:
                     tiktok_service.close_sync() # 确保资源被清理

        else:
            raise MediaError(f"不支持的媒体平台: {platform}")

        if media_data is None: # 双重检查
             raise MediaError("未能获取任何媒体数据")

        logger.info(f"[Fetch Basic {trace_id=}] 基础信息获取成功. Platform={platform}", extra=log_extra)
        return {"status": "success", "data": media_data, "points_consumed": base_cost}

    # --- 统一错误处理 ---
    except (XHSError, TikTokError, MediaError, InitializationError, VideoFetchError) as e:
        error_msg = f"获取基础信息失败 ({type(e).__name__}): {str(e)}"
        logger.error(f"[Fetch Basic {trace_id=}] {error_msg}", extra=log_extra, exc_info=False)
        return {"status": "failed", "error": error_msg, "points_consumed": 0}
    except Exception as e:
        error_msg = f"获取基础信息时发生意外错误: {str(e)}"
        logger.error(f"[Fetch Basic {trace_id=}] {error_msg}", exc_info=True, extra=log_extra)
        return {"status": "failed", "error": f"发生内部错误 ({trace_id})", "exception": str(e), "points_consumed": 0}


# --- 2. 准备媒体以供转写 (适用于 Task A - extract_text=True) ---
# 注意：这个函数有副作用（下载文件），缓存需要谨慎使用或不使用。
# 如果要缓存，可能只缓存基础信息部分，下载步骤总是执行。
# 这里暂时不加缓存。
def prepare_media_for_transcription(
    platform: str,
    url: str,
    include_comments: bool,
    user_id: str,
    trace_id: str,
    app_id: str
) -> dict:
    """
    [同步执行] 获取媒体基础信息，并下载需要转写的音频文件到共享路径。
    不执行转写。
    """
    log_extra = {"request_id": trace_id, "user_id": user_id, "app_id": app_id, "logic_step": "prepare_transcription"}
    logger.info(f"[Prepare Transcription {trace_id=}] 开始准备阶段: platform={platform}, url={url}", extra=log_extra)

    audio_path = None
    media_url_to_download = None

    # 1. 获取基础信息
    basic_info_result = fetch_basic_media_info( # 调用上面的函数 (会利用缓存)
        platform=platform,
        url=url,
        include_comments=include_comments,
        user_id=user_id,
        trace_id=trace_id,
        app_id=app_id
    )

    if basic_info_result.get("status") != "success":
        logger.error(f"[Prepare Transcription {trace_id=}] 获取基础信息失败，准备阶段中止。", extra=log_extra)
        return basic_info_result # 直接返回失败信息

    basic_info_data = basic_info_result.get("data")
    base_points_consumed = basic_info_result.get("points_consumed", 0)

    if not isinstance(basic_info_data, dict): # 健壮性检查
        logger.error(f"[Prepare Transcription {trace_id=}] 获取的基础信息格式不正确 (非字典)", extra=log_extra)
        return {"status": "failed", "error": "内部错误：基础信息格式错误", "points_consumed": 0}


    # 2. 检查是否是视频类型，并获取下载链接
    media_type = basic_info_data.get("type", "").lower() 
    if not media_type :
        media_type = basic_info_data.get("data").get("type").lower()

    if media_type != MediaType.VIDEO.lower():        
        logger.warning(f"[Prepare Transcription {trace_id=}] 媒体类型不是视频 ({media_type}), 无法进行转写准备。", extra=log_extra)
        # 对于非视频，准备阶段可以认为"成功"但没有音频路径，或者标记为不适用？
        # 返回成功，让 Task A 判断 audio_path 是否存在可能更好
        return {
            "status": "success",
            "data": {"basic_info": basic_info_data, "audio_path": None}, # audio_path 为 None
            "points_consumed": base_points_consumed,
            "message": "媒体非视频类型，无需准备转写"
        }

    try:
        # 根据平台获取合适的下载链接
        if platform == MediaPlatform.XIAOHONGSHU:
            media_url_to_download = basic_info_data.get("media", {}).get("video_url")
        elif platform == MediaPlatform.DOUYIN:
            # 抖音可能优先使用无水印链接或其他下载链接
            media_url_to_download = basic_info_data.get("data").get("downloads") or basic_info_data.get("media_url")
        else:
            media_url_to_download = basic_info_data.get("media_url")  # 通用尝试

        if not media_url_to_download:
            logger.error(f"[Prepare Transcription {trace_id=}] 未能在基础信息中找到有效的视频/音频下载链接", extra=log_extra)
            return {"status": "failed", "error": "无法找到下载链接", "data": {"basic_info": basic_info_data}, "points_consumed": base_points_consumed}

        # 3. 下载音频文件
        logger.info(f"[Prepare Transcription {trace_id=}] 开始下载音频文件从: {media_url_to_download}", extra=log_extra)
        script_service = ScriptService()  # 实例化下载/转写服务
        
        # 根据平台选择不同的下载方法
        if platform == MediaPlatform.DOUYIN:
            audio_path= script_service.download_media_sync(media_url_to_download,trace_id)
        else:
            # 对于其他平台使用通用下载方法
            audio_path, _ = script_service.download_audio_sync(media_url_to_download, trace_id)
        
        if not audio_path or not os.path.exists(audio_path):  # 检查路径有效性
            raise AudioDownloadError("下载服务未返回有效路径或文件不存在")
        
        logger.info(f"[Prepare Transcription {trace_id=}] 音频文件下载成功: {audio_path}", extra=log_extra)
    
        # 准备成功
        return {
            "status": "success",
            "data": {"basic_info": basic_info_data, "audio_path": audio_path},
            "points_consumed": base_points_consumed  # 准备阶段只计算基础积分
        }

    except AudioDownloadError as e:
        error_msg = f"下载音频文件失败: {str(e)}"
        logger.error(f"[Prepare Transcription {trace_id=}] {error_msg}", extra=log_extra)
        return {"status": "failed", "error": error_msg, "data": {"basic_info": basic_info_data}, "points_consumed": base_points_consumed}
    except Exception as e:
        error_msg = f"下载音频时发生意外错误: {str(e)}"
        logger.error(f"[Prepare Transcription {trace_id=}] {error_msg}", exc_info=True, extra=log_extra)
        return {"status": "failed", "error": f"下载时发生内部错误 ({trace_id})", "exception": str(e), "data": {"basic_info": basic_info_data}, "points_consumed": base_points_consumed}

# --- 3. 音频转写逻辑 (假设主要在 ScriptService 中) ---
# Task B 会直接调用类似 script_service.transcribe_audio_sync 的方法
# 这里不需要再封装一层，除非有额外的业务逻辑

# --- (内部辅助函数/类，例如 CeleryTikTokService 中的 _run_fetch_in_thread) ---
# 这些需要根据你的具体实现来放置和调整
# 例如，CeleryTikTokService 可能需要一个内部同步方法来调用异步 fetch 逻辑