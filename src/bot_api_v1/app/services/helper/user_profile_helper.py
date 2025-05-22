from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.media_extrat_format import Media_extract_format
from bot_api_v1.app.services.business.media_service import MediaService
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.cache import async_cache_result

media_service = MediaService()
formatter = Media_extract_format()

class UserProfileHelper:
    def __init__(self):
        pass

    @async_cache_result(expire_seconds=600,prefix="user_profile_helper")
    async def get_user_profile_logic(self, user_url):
        trace_key = request_ctx.get_trace_key()
        user_id = request_ctx.get_cappa_user_id()
        app_id = request_ctx.get_app_id()
        platform = formatter._identify_platform(user_url)
        log_extra = {"request_id": trace_key, "user_id": user_id, "app_id": app_id, "platform": platform, "user_url": user_url}
        
        try:
            result = await media_service.get_user_profile(user_url, log_extra)
            return result
        except Exception as e:
            logger.error(f"get_user_profile_logic-获取用户主页信息失败: {str(e)}", extra=log_extra)
            raise