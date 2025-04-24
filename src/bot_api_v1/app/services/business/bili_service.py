import re
from typing import Dict, Any, Optional, Tuple, Union, List
from datetime import datetime
import yt_dlp

from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
import json
from bot_api_v1.app.utils.media_extrat_format import Media_extract_format

class BiliService_Async:
    def __init__(self):
        pass



class BiliService_Sync:
    """
    同步处理 Bilibili 服务的类
    使用阻塞操作，适合在同步代码或后台任务 (如 Celery) 中使用
    """
    def __init__(self):
        """
        初始化同步服务类
        """
        # 可以在这里进行一些初始化操作，比如配置 yt-dlp 路径等 (如果需要)
        pass

    
    
    def get_basic_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        使用 yt-dlp 获取 Bilibili 视频的基础信息，并返回统一 schema。
        """
        logger.info(f"开始使用 yt-dlp (Python API) 获取视频信息: {url}")
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                logger.error(f"yt-dlp 未返回任何信息。URL: {url}")
                return None

            media_extract_format = Media_extract_format()
            # 构造 schema
            schema = {
                "platform": "bilibili",
                "video_id": info.get("id", ""),
                "original_url": url,
                "title": info.get("title", ""),
                "description": info.get("description", ""),
                "content": "",  # B站基础信息阶段无转写文本
                "tags": info.get("tags", []),
                "author": {
                    "id": info.get("uploader_id", ""),
                    "sec_uid": "",  # B站无 sec_uid
                    "nickname": info.get("uploader", ""),
                    "avatar": info.get("uploader_avatar", ""),  # 可能没有，yt-dlp 可能无此字段
                    "signature": "",  # B站无 signature
                    "verified": info.get("uploader_verified", False),
                    "follower_count": 0,  # yt-dlp 不提供
                    "following_count": 0,
                    "region": ""
                },
                "statistics": {
                    "like_count": info.get("like_count", 0),
                    "comment_count": info.get("comment_count", 0),
                    "share_count": info.get("repost_count", 0),
                    "collect_count": info.get("favorite_count", 0),
                    "play_count": info.get("view_count", 0)
                },
                "media": {
                    "cover_url": info.get("thumbnail", ""),
                    "video_url": info.get("url", ""),
                    "duration": round(info.get("duration", 0)),
                    "width": info.get("width", 0),
                    "height": info.get("height", 0),
                    "quality": info.get("format_note", "normal")
                },
                "publish_time": media_extract_format._format_timestamp(info.get("timestamp", 0)),
                "update_time": None
            }
            logger.info(f"成功获取视频基础信息: {schema.get('title')} (ID: {schema.get('video_id')})")
            return schema
        except Exception as e:
            logger.error(f"获取 Bilibili 视频信息时发生异常 (yt-dlp Python API)。URL: {url}, 错误: {str(e)}", exc_info=True)
            return None


    def down_media(self, url: str):
        """
        下载 Bilibili 视频或音频 (占位)
        未来可以使用 yt-dlp 或其他库来实现下载功能
        """
        logger.warning(f"down_media 方法尚未实现。 URL: {url}")
        pass

    def get_transcribed_text(self, url: str):
        """
        获取 Bilibili 视频的字幕或转录文本 (占位)
        未来可以使用 yt-dlp 或其他语音识别服务实现
        """
        logger.warning(f"get_transcribed_text 方法尚未实现。 URL: {url}")
        pass

# --- 示例用法 ---
if __name__ == "__main__":
    # 创建服务实例
    bili_sync_service = BiliService_Sync()

    # 测试用的 Bilibili 视频链接 (请替换为有效的链接)
    # test_url = "https://www.bilibili.com/video/BV1..." # 替换这里
    test_url = "https://www.bilibili.com/video/BV1EV5iznEQZ?spm_id_from=333.1007.tianma.3-2-6.click" # 示例：一个公开的 B站视频

    # 调用方法获取信息
    video_info = bili_sync_service.get_basic_info(test_url)

    # 打印结果
    if video_info:
        print("\n--- 视频基础信息 ---")
        # 为了更美观地打印字典，可以使用 json.dumps
        print(json.dumps(video_info, indent=4, ensure_ascii=False))
    else:
        print(f"\n无法获取视频信息: {test_url}")

    # 可以在这里添加更多测试用例，包括无效链接、超时的场景等
    # invalid_url = "https://invalid-url"
    # print(f"\n测试无效 URL: {invalid_url}")
    # bili_sync_service.get_basic_info(invalid_url)