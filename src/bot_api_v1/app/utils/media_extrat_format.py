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

from bot_api_v1.app.constants.media_info import MediaPlatform

class Media_extract_format:
    def __init__(self):
        pass


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
        
        return list(set(tags))  

    
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

    
    def _identify_platform(self, url: str) -> str:
        """
        识别URL对应的平台
        
        Args:
            url: 媒体URL
            
        Returns:
            平台标识: "douyin", "xiaohongshu" 或 "unknown"
        """
        url = url.lower()
        
        # 抖音URL模式
        if any(domain in url for domain in ["douyin.com", "iesdouyin.com"]):
            return MediaPlatform.DOUYIN
            
        # 小红书URL模式
        if any(domain in url for domain in ["xiaohongshu.com", "xhslink.com", "xhs.cn"]):
            return MediaPlatform.XIAOHONGSHU

        # 
        if any(domain in url for domain in ["bilibili.com", "bilibili.com", "bilibili.cn"]):
            return MediaPlatform.BILIBILI


        if any(domain in url for domain in ["youtu.be", "youtube.com"]):
            return MediaPlatform.YOUTUBE
            

        if any(domain in url for domain in ["instagram.com"]):
            return MediaPlatform.INSTAGRAM

        if any(domain in url for domain in ["tiktok.com"]):
            return MediaPlatform.TIKTOK

        if any(domain in url for domain in ["kuaishou.com"]):
            return MediaPlatform.KUAISHOU
            
        # 未知平台
        return MediaPlatform.UNKNOWN