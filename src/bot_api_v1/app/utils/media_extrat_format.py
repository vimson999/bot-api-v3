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


class Media_extract_format:
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