import re
from typing import Dict, Any, Optional, Tuple, Union, List
from datetime import datetime

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.core.cache import cache_result
from bot_api_v1.app.services.business.douyin_service import DouyinService, DouyinError
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper

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
        self.douyin_service = DouyinService()
    
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
    @cache_result(expire_seconds=3600, prefix="media_extract")
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
            if isinstance(e, (DouyinError, MediaError)):
                raise MediaError(error_msg) from e
            raise MediaError(f"未知错误: {error_msg}") from e
    
    async def _process_douyin(self, url: str, extract_text: bool, include_comments: bool) -> Dict[str, Any]:
        """处理抖音内容"""
        trace_key = request_ctx.get_trace_key()
        logger.info(f"处理抖音内容: {url}", extra={"request_id": trace_key})
        
        # 调用抖音服务获取视频信息
        video_info = await self.douyin_service.get_video_info(url, extract_text=extract_text)
        
        # 转换为统一结构
        result = {
            "platform": MediaPlatform.DOUYIN,
            "video_id": video_info.get("aweme_id", ""),
            "original_url": url,
            "title": video_info.get("desc", ""),
            "description": video_info.get("desc", ""),
            "content": video_info.get("transcribed_text", "") if extract_text else "",
            "tags": self._extract_tags_from_douyin(video_info),
            
            "author": {
                "id": video_info.get("author", {}).get("uid", ""),
                "sec_uid": video_info.get("author", {}).get("sec_uid", ""),
                "nickname": video_info.get("author", {}).get("nickname", ""),
                "avatar": video_info.get("author", {}).get("avatar", ""),
                "signature": video_info.get("author", {}).get("signature", ""),
                "verified": video_info.get("author", {}).get("is_verified", False),
                "follower_count": video_info.get("author", {}).get("total_favorited", 0),
                "following_count": video_info.get("author", {}).get("favoriting_count", 0),
                "region": video_info.get("author", {}).get("region", "")
            },
            
            "statistics": {
                "like_count": video_info.get("statistics", {}).get("digg_count", 0),
                "comment_count": video_info.get("statistics", {}).get("comment_count", 0),
                "share_count": video_info.get("statistics", {}).get("share_count", 0),
                "collect_count": video_info.get("statistics", {}).get("collect_count", 0),
                "play_count": video_info.get("statistics", {}).get("play_count", 0)
            },
            
            "media": {
                "cover_url": video_info.get("cover_url", ""),
                "video_url": video_info.get("video_url", ""),
                "duration": video_info.get("duration", 0),
                "width": video_info.get("video", {}).get("width", 0),
                "height": video_info.get("video", {}).get("height", 0),
                "quality": "normal"
            },
            
            "publish_time": self._format_timestamp(video_info.get("create_time", 0)),
            "update_time": None
        }
        
        return result
    
    async def _process_xiaohongshu(self, url: str, extract_text: bool, include_comments: bool) -> Dict[str, Any]:
        """处理小红书内容 (临时Mock实现)"""
        trace_key = request_ctx.get_trace_key()
        logger.info(f"处理小红书内容(mock): {url}", extra={"request_id": trace_key})
        
        # 从URL中提取ID或使用随机ID
        video_id = url.split('/')[-1] if '/' in url else "mock_id_123456"
        
        # 返回Mock数据
        current_time = datetime.now().isoformat()
        
        return {
            "platform": MediaPlatform.XIAOHONGSHU,
            "video_id": video_id,
            "original_url": url,
            "title": "小红书测试视频标题",
            "description": "这是一段小红书视频的详细描述，用于展示小红书内容的结构和格式。",
            "content": "这是一段小红书视频的测试文案内容。Mock数据仅用于测试统一API功能。" if extract_text else "",
            "tags": ["测试", "小红书", "视频"],
            
            "author": {
                "id": "user_xhs_123456",
                "sec_uid": "xhs_sec_id_abcdef",
                "nickname": "小红书测试用户",
                "avatar": "https://example.com/avatar.jpg",
                "signature": "这是一个测试签名",
                "verified": True,
                "follower_count": 10000,
                "following_count": 500,
                "region": "上海"
            },
            
            "statistics": {
                "like_count": 1500,
                "comment_count": 120,
                "share_count": 45,
                "collect_count": 800,
                "play_count": 5000
            },
            
            "media": {
                "cover_url": "https://example.com/cover.jpg",
                "video_url": url,
                "duration": 60,
                "width": 1080,
                "height": 1920,
                "quality": "high"
            },
            
            "publish_time": current_time,
            "update_time": current_time
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