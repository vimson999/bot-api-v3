from bot_api_v1.app.services.business.media_service import MediaPlatform, MediaError
from bot_api_v1.app.services.business.xhs_service import XHSService, XHSError 
from bot_api_v1.app.services.business.tiktok_service import TikTokService, TikTokError, InitializationError
from bot_api_v1.app.services.business.script_service import ScriptService, AudioDownloadError, AudioTranscriptionError

from bot_api_v1.app.core.logger import logger
import time
import os
import asyncio 

# !! 导入新的同步缓存装饰器 !!
from bot_api_v1.app.core.cache import cache_result_sync 
from bot_api_v1.app.core.config import settings

@cache_result_sync(
    expire_seconds= 10, # 使用配置或默认 30 分钟
    prefix="celery_media_extract_sync",
    skip_args=['trace_id', 'user_id', 'app_id'] 
)
def execute_media_extraction_sync(
    url: str,
    extract_text: bool,
    include_comments: bool,
    platform: str,
    user_id: str,
    trace_id: str,
    app_id: str
) -> dict:
    """
    [同步执行] 分发器：调用平台特定的同步提取方法。
    """
    log_extra = {"request_id": trace_id, "user_id": user_id, "app_id": app_id}
    logger.info(f"[Sync Dispatcher {trace_id=}] 分发任务: platform={platform}, url={url}", extra=log_extra)

    try:
        if platform == MediaPlatform.XIAOHONGSHU:
            # 注意：每次调用都实例化可能效率低，后续可优化
            xhs_service = XHSService() 
            result_dict = xhs_service.get_note_info_sync_for_celery(
                url=url, 
                extract_text=extract_text, 
                user_id_for_points=user_id, 
                trace_id=trace_id
            )

            # result_dict["data"]["platform"] = MediaPlatform.XIAOHONGSHU
        elif platform == MediaPlatform.DOUYIN:
            try:
                 # 实例化是轻量级的，初始化和清理在 __enter__ / __exit__ 中
                 with TikTokService() as tiktok_service_instance: # 调用 __enter__
                      result_dict = tiktok_service_instance.get_video_info_sync_for_celery( # 调用新增的同步方法
                          url=url, 
                          extract_text=extract_text,
                          user_id_for_points=user_id,
                          trace_id=trace_id
                      )
                 # 离开 with 块时自动调用 __exit__ 进行清理
            except InitializationError as init_e:
                 # 捕获同步初始化期间的错误
                 raise TikTokError(f"TikTok 服务同步初始化失败: {init_e}") from init_e
            # 其他 TikTokError 会在下面被捕获
        else:
            raise MediaError(f"不支持的媒体平台: {platform}")

        logger.info(f"[Sync Dispatcher {trace_id=}] 平台逻辑执行完成. Status: {result_dict.get('status')}", extra=log_extra)
        return result_dict

    except (XHSError, TikTokError, MediaError, InitializationError) as e:
        error_msg = f"处理失败 ({type(e).__name__}): {str(e)}"
        logger.error(f"[Sync Dispatcher {trace_id=}] {error_msg}", extra=log_extra)
        return {"status": "failed", "error": error_msg, "points_consumed": 0}
    except Exception as e:
        error_msg = f"分发或执行时发生意外错误: {str(e)}"
        logger.error(f"[Sync Dispatcher {trace_id=}] {error_msg}", exc_info=True, extra=log_extra)
        return {"status": "failed", "error": f"发生内部错误 ({trace_id})", "exception": str(e), "points_consumed": 0}
