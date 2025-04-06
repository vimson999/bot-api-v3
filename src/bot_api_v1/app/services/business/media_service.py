import re
from typing import Dict, Any, Optional, Tuple, Union, List
from datetime import datetime

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.core.cache import cache_result
# from bot_api_v1.app.services.business.douyin_service import DouyinService, DouyinError
from bot_api_v1.app.services.business.tiktok_service import TikTokService, TikTokError
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
from bot_api_v1.app.services.business.xhs_service import XHSService

class MediaPlatform:
    """媒体平台枚举"""
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"
    UNKNOWN = "unknown"

class MediaError(Exception):
    """媒体处理错误"""
    pass

class MediaService:
    """统一媒体内容提取服务"""
    
    def __init__(self):
        """初始化服务"""
        # self.douyin_service = DouyinService()
        self.tiktok_service = TikTokService()
        self.xhs_service = XHSService()  # 使用新的XHSService
    
    def identify_platform(self, url: str) -> str:
        """
        识别URL对应的平台
        
        Args:
            url: 媒体URL
            
        Returns:
            平台标识: "douyin", "xiaohongshu" 或 "unknown"
        """
        url = url.lower()
        
        # 抖音URL模式
        if any(domain in url for domain in ["douyin.com", "iesdouyin.com", "tiktok.com"]):
            return MediaPlatform.DOUYIN
            
        # 小红书URL模式
        if any(domain in url for domain in ["xiaohongshu.com", "xhslink.com", "xhs.cn"]):
            return MediaPlatform.XIAOHONGSHU
            
        # 未知平台
        return MediaPlatform.UNKNOWN
    
    @gate_keeper()
    @log_service_call(method_type="media", tollgate="10-2")
    @cache_result(expire_seconds=600, prefix="media_extract")
    async def extract_media_content(self, url: str, extract_text: bool = True, include_comments: bool = False) -> Dict[str, Any]:
        """
        提取媒体内容信息
        
        Args:
            url: 媒体URL
            extract_text: 是否提取文案
            include_comments: 是否包含评论
            
        Returns:
            Dict: 媒体内容信息
            
        Raises:
            MediaError: 处理过程中出现的错误
        """
        trace_key = request_ctx.get_trace_key()
        
        # 识别平台
        platform = self.identify_platform(url)
        logger.info(f"识别URL平台: {url} -> {platform}", extra={"request_id": trace_key})
        

        try:
            if platform == MediaPlatform.DOUYIN:
                return await self._process_douyin(url, extract_text, include_comments)
            elif platform == MediaPlatform.XIAOHONGSHU:
                return await self._process_xiaohongshu(url, extract_text, include_comments)
            else:
                raise MediaError(f"不支持的媒体平台: {url}")
        except Exception as e:
            error_msg = f"处理媒体内容时出错: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            if isinstance(e, (TikTokError, MediaError)):
                raise MediaError(error_msg) from e
            raise MediaError(f"未知错误: {error_msg}") from e
    
    async def _process_douyin(self, url: str, extract_text: bool, include_comments: bool) -> Dict[str, Any]:
        """处理抖音内容"""
        trace_key = request_ctx.get_trace_key()
        logger.info_to_db(f"处理抖音内容: {url}", extra={"request_id": trace_key})
        
        # 使用 async with 语句正确初始化 TikTokService
        async with self.tiktok_service as service:
            # 调用抖音服务获取视频信息
            video_info = await service.get_video_info(url,extract_text=extract_text)        

        duration = self._convert_time_to_seconds(video_info.get("duration", 0))
        # 转换为统一结构
        result = {
            "platform": MediaPlatform.DOUYIN,
            "video_id": video_info.get("id", ""),  # 使用 id 字段
            "original_url": url,
            "title": video_info.get("desc", ""),
            "description": video_info.get("desc", ""),
            "content": video_info.get("transcribed_text", "") if extract_text else "",
            "tags": self._extract_tags_from_douyin(video_info),
            
            "author": {
                "id": video_info.get("uid", ""),  # 直接从顶层获取
                "sec_uid": video_info.get("sec_uid", ""),  # 直接从顶层获取
                "nickname": video_info.get("nickname", ""),  # 直接从顶层获取
                "avatar": "",  # 视频信息中可能没有头像URL
                "signature": video_info.get("signature", ""),  # 直接从顶层获取
                "verified": False,  # 默认为False
                "follower_count": 0,  # 视频信息中可能没有粉丝数
                "following_count": 0,  # 视频信息中可能没有关注数
                "region": ""  # 视频信息中可能没有地区信息
            },
            
            "statistics": {
                "like_count": video_info.get("digg_count", 0),  # 直接从顶层获取
                "comment_count": video_info.get("comment_count", 0),  # 直接从顶层获取
                "share_count": video_info.get("share_count", 0),  # 直接从顶层获取
                "collect_count": video_info.get("collect_count", 0),  # 直接从顶层获取
                "play_count": video_info.get("play_count", 0)  # 直接从顶层获取
            },
            
            "media": {
                "cover_url": video_info.get("origin_cover", ""),  # 使用原始封面
                "video_url": video_info.get("downloads", ""),  # 使用下载链接
                "duration": duration,
                "width": video_info.get("width", 0),  # 直接从顶层获取
                "height": video_info.get("height", 0),  # 直接从顶层获取
                "quality": "normal"
            },
            
            "publish_time": self._format_timestamp(video_info.get("create_timestamp", 0)),
            "update_time": None
        }

        return result
    
    async def _process_xiaohongshu(self, url: str, extract_text: bool, include_comments: bool) -> Dict[str, Any]:
        """处理小红书内容"""
        trace_key = request_ctx.get_trace_key()
        logger.info_to_db(f"处理小红书内容: {url}", extra={"request_id": trace_key})
        
        try:
            # 调用XHSService获取小红书笔记信息
            note_info = await self.xhs_service.get_note_info(url, extract_text=extract_text)
            
            # 转换为统一结构
            result = {
                "platform": MediaPlatform.XIAOHONGSHU,
                "video_id": note_info.get("note_id", ""),
                "original_url": url,
                "title": note_info.get("title", ""),
                "description": note_info.get("desc", ""),
                "content": note_info.get("transcribed_text", "") if extract_text else "",
                "tags": note_info.get("tags", []),
                
                "author": {
                    "id": note_info.get("author", {}).get("id", ""),
                    "sec_uid": note_info.get("author", {}).get("user_id", ""),
                    "nickname": note_info.get("author", {}).get("nickname", ""),
                    "avatar": note_info.get("author", {}).get("avatar", ""),
                    "signature": note_info.get("author", {}).get("signature", ""),
                    "verified": note_info.get("author", {}).get("verified", False),
                    "follower_count": note_info.get("author", {}).get("follower_count", 0),
                    "following_count": note_info.get("author", {}).get("following_count", 0),
                    "region": note_info.get("author", {}).get("location", "")
                },
                
                "statistics": {
                    "like_count": note_info.get("statistics", {}).get("like_count", 0),
                    "comment_count": note_info.get("statistics", {}).get("comment_count", 0),
                    "share_count": note_info.get("statistics", {}).get("share_count", 0),
                    "collect_count": note_info.get("statistics", {}).get("collected_count", 0),
                    "play_count": note_info.get("statistics", {}).get("view_count", 0)
                },
                
                "media": {
                    "cover_url": note_info.get("media", {}).get("cover_url", ""),
                    "video_url": note_info.get("media", {}).get("video_url", ""),
                    "duration": note_info.get("media", {}).get("duration", 0),
                    "width": note_info.get("media", {}).get("width", 0),
                    "height": note_info.get("media", {}).get("height", 0),
                    "quality": "normal"
                },
                
                "publish_time": self._format_timestamp(note_info.get("create_time", 0)),
                "update_time": self._format_timestamp(note_info.get("last_update_time", 0))
            }
            
            return result
            
        except Exception as e:
            # 记录错误并返回基本信息
            error_msg = f"处理小红书内容时出错: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            
            # 从URL中提取ID或使用随机ID
            video_id = url.split('/')[-1] if '/' in url else "mock_id_123456"
            current_time = datetime.now().isoformat()
            
            # 返回出错时的默认信息
            return {
                "platform": MediaPlatform.XIAOHONGSHU,
                "video_id": video_id,
                "original_url": url,
                "title": "小红书内容 (处理失败)",
                "description": f"提取内容失败: {str(e)}",
                "content": "",
                "tags": [],
                "author": {
                    "id": "",
                    "sec_uid": "",
                    "nickname": "未知用户",
                    "avatar": "",
                    "signature": "",
                    "verified": False,
                    "follower_count": 0,
                    "following_count": 0,
                    "region": ""
                },
                "statistics": {
                    "like_count": 0,
                    "comment_count": 0,
                    "share_count": 0,
                    "collect_count": 0,
                    "play_count": 0
                },
                "media": {
                    "cover_url": "",
                    "video_url": "",
                    "duration": 0,
                    "width": 0,
                    "height": 0,
                    "quality": ""
                },
                "publish_time": current_time,
                "update_time": current_time,
                "error": error_msg
            }
    
    def _extract_tags_from_douyin(self, video_info: Dict[str, Any]) -> List[str]:
        """从抖音视频信息中提取标签"""
        tags = []
        
        # 尝试从描述中提取话题标签 (#xxx)
        desc = video_info.get("desc", "")
        if desc:
            hashtags = re.findall(r'#(\w+)', desc)
            tags.extend(hashtags)
        
        # 如果有专门的标签字段，也添加它们
        if "text_extra" in video_info and isinstance(video_info["text_extra"], list):
            for item in video_info["text_extra"]:
                if "hashtag_name" in item and item["hashtag_name"]:
                    tags.append(item["hashtag_name"])
        
        return list(set(tags))  # 去重
    
    def _convert_time_to_seconds(self, time_str: Union[str, int, float]) -> int:
            """
            将时间字符串转换为秒数
            
            Args:
                time_str: 时间字符串 (如 "00:01:31") 或数值
                
            Returns:
                int: 秒数
            """
            if isinstance(time_str, (int, float)):
                return int(time_str)
                
            if not isinstance(time_str, str):
                return 0
                
            try:
                # 处理 "00:01:31" 格式
                if ":" in time_str:
                    parts = time_str.split(":")
                    if len(parts) == 3:  # 时:分:秒
                        hours, minutes, seconds = map(int, parts)
                        return hours * 3600 + minutes * 60 + seconds
                    elif len(parts) == 2:  # 分:秒
                        minutes, seconds = map(int, parts)
                        return minutes * 60 + seconds
                
                # 尝试直接转换为整数
                return int(float(time_str))
            except (ValueError, TypeError):
                logger.warning(f"无法解析时间字符串: {time_str}，使用默认值0")
                return 0

    def _format_timestamp(self, timestamp: Union[int, float, None]) -> Optional[str]:
        """格式化时间戳为ISO格式字符串"""
        if not timestamp:
            return None
            
        try:
            # 处理秒级和毫秒级时间戳
            if timestamp > 10000000000:  # 毫秒级
                timestamp = timestamp / 1000
                
            return datetime.fromtimestamp(timestamp).isoformat()
        except:
            return None