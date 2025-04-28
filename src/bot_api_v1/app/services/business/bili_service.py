import re
import os
import time
from typing import Dict, Any, Optional, Tuple, Union, List
from datetime import datetime
import yt_dlp

from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
import json

from bot_api_v1.app.services.business.yt_dlp_service import YtDLP_Service_Sync

class AudioDownloadError(Exception):
    """音频下载过程中出现的错误"""
    pass

class BiliService_Async:
    def __init__(self):
        pass



class BiliService_Sync:
    """
    同步处理 Bilibili 服务的类
    使用阻塞操作，适合在同步代码或后台任务 (如 Celery) 中使用
    """
    def __init__(self):
        self.ytdlp_sync = YtDLP_Service_Sync()

    def get_basic_info(self, url: str, task_id: str = "", log_extra: dict = None) -> Optional[Dict[str, Any]]:
        """
        调用 YtDLP_Service_Sync 获取 Bilibili 视频的基础信息。
        """
        if log_extra is None:
            log_extra = {}
        return self.ytdlp_sync.get_basic_info(task_id=task_id, url=url, log_extra=log_extra)

    def down_media(self, url: str, task_id: str = "", log_extra: dict = None):
        """
        调用 YtDLP_Service_Sync 下载 Bilibili 视频音频。
        """
        if log_extra is None:
            log_extra = {}
        return self.ytdlp_sync.down_media(task_id=task_id, url=url, log_extra=log_extra)


    def get_transcribed_text(
        self, 
        media_url_to_download:str, 
        platform:str ,
        original_url: str,
        audio_path: str, 
        trace_id: str
    ):
        return self.ytdlp_sync.get_transcribed_text(media_url_to_download=media_url_to_download, platform=platform, original_url=original_url, audio_path=audio_path, trace_id=trace_id)



# # --- 示例用法 ---
# if __name__ == "__main__":
#     # 创建服务实例
#     bili_sync_service = BiliService_Sync()

#     # 测试用的 Bilibili 视频链接 (请替换为有效的链接)
#     # test_url = "https://www.bilibili.com/video/BV1..." # 替换这里
#     test_url = "https://www.bilibili.com/video/BV1EV5iznEQZ?spm_id_from=333.1007.tianma.3-2-6.click" # 示例：一个公开的 B站视频

#     # 调用方法获取信息
#     video_info = bili_sync_service.get_basic_info(test_url)
#     actual_downloaded_path, downloaded_title = bili_sync_service.down_media(video_info.get("media").get("video_url"))

#     # def transcribe_audio_sync(self, media_url_to_download:str, platform:str ,original_url: str,audio_path: str, trace_id: str) -> str:
#     content = bili_sync_service.get_transcribed_text(
#             media_url_to_download = test_url,platform="bilibili",
#             original_url=test_url,
#             audio_path=actual_downloaded_path,
#             trace_id="")

#     video_info["content"] = content.get("text")

#     # 打印结果
#     if video_info:
#         print("\n--- 视频基础信息 ---")
#         # 为了更美观地打印字典，可以使用 json.dumps
#         print(json.dumps(video_info, indent=4, ensure_ascii=False))
#     else:
#         print(f"\n无法获取视频信息: {test_url}")

    # 可以在这里添加更多测试用例，包括无效链接、超时的场景等
    # invalid_url = "https://invalid-url"
    # print(f"\n测试无效 URL: {invalid_url}")
    # bili_sync_service.get_basic_info(invalid_url)