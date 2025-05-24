from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.media_extrat_format import Media_extract_format
from bot_api_v1.app.services.business.media_service import MediaService
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.cache import async_cache_result

media_service = MediaService()
formatter = Media_extract_format()

class VideoCommentHelper:
    def __init__(self):
        pass

    # @async_cache_result(expire_seconds=600,prefix="video_comment_helper")
    async def get_video_comment_list(self, video_url):
        trace_key = request_ctx.get_trace_key()
        user_id = request_ctx.get_cappa_user_id()
        app_id = request_ctx.get_app_id()
        platform = formatter._identify_platform(video_url)
        log_extra = {"request_id": trace_key, "user_id": user_id, "app_id": app_id, "platform": platform, "video_url": video_url}
        
        try:
            result = await media_service.async_get_comment_by_url(video_url, log_extra)
            return result
        except Exception as e:
            logger.error(f"get_video_comment_list-获取用户主页信息失败: {str(e)}", extra=log_extra)
            raise