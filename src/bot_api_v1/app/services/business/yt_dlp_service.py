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

from bot_api_v1.app.services.business import script_service_sync
from bot_api_v1.app.utils.media_extrat_format import Media_extract_format
from bot_api_v1.app.constants.media_info import MediaType
from bot_api_v1.app.services.business.script_service_sync import ScriptService_Sync
from bot_api_v1.app.services.business.open_router_service import OpenRouterService
from openai import OpenAI


class AudioDownloadError(Exception):
    """音频下载过程中出现的错误"""
    pass



class YtDLP_Service_Sync:
    def __init__(self):
        pass
    
    def get_basic_info(
        self, 
        task_id: str,
        url: str,
        log_extra: dict
    ) -> Optional[Dict[str, Any]]:
        """
        使用 yt-dlp 获取视频的基础信息，并返回统一 schema。
        """
        logger.info(f"[{task_id}] 开始获取视频基础信息: {url}", extra=log_extra)
        ydl_opts = {
            # "quiet": True,
            # "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }
        media_extract_format = Media_extract_format()
        platform = media_extract_format._identify_platform(url)
        logger.debug(f'current platform: {platform}')

        # 新增：如果是tiktok，读取cookie文件
        if platform == "tiktok":
            cookie_path = settings.TIKTOK_COOKIE_FILE
            if os.path.exists(cookie_path):
                ydl_opts["cookiefile"] = cookie_path
            else:
                logger.warning(f"[{task_id}] tiktok平台未找到cookie文件: {cookie_path}", extra=log_extra)

                
        try:
            logger.debug(f"[{task_id}] 使用的 ydl_opts: {ydl_opts}", extra=log_extra) # 添加这行日志
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                logger.error(f"[{task_id}] yt-dlp 未返回任何信息。URL: {url}", extra=log_extra)
                return None

            media_extract_format = Media_extract_format()
            schema = {
                "platform": platform,
                "video_id": info.get("id", ""),
                "original_url": url,
                "title": info.get("title", ""),
                "description": info.get("description", ""),
                "content": "",
                "tags": info.get("tags", []),
                "type":MediaType.VIDEO.lower(),
                "author": {
                    "id": info.get("uploader_id", ""),
                    "sec_uid": "",
                    "nickname": info.get("uploader", ""),
                    "avatar": info.get("uploader_avatar", ""),
                    "signature": "",
                    "verified": info.get("uploader_verified", False),
                    "follower_count": 0,
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
                    "video_url": info.get("url", url),
                    "duration": round(info.get("duration", 0)),
                    "width": info.get("width", 0),
                    "height": info.get("height", 0),
                    "quality": info.get("format_note", "normal")
                },
                "publish_time": media_extract_format._format_timestamp(info.get("timestamp", 0)),
                "update_time": None
            }
            logger.info(f"[{task_id}] 成功获取视频基础信息: 标题={schema.get('title')}, 视频ID={schema.get('video_id')}, 平台={platform}", extra=log_extra)
            return schema
        except Exception as e:
            logger.error(f"[{task_id}] 获取视频信息异常: {type(e).__name__} - {str(e)}，URL: {url}", exc_info=True, extra=log_extra)
            return None

    # def get_schema(self, note_info: Dict[str, Any]) -> Dict[str, Any]:
    #     try:
    #         # 判断笔记类型
    #         note_type = note_info.get('note_type', '')
    #         is_video = note_type == NoteType.VIDEO
            
    #         # 构造媒体信息
    #         media_info = {
    #             "cover_url": note_info.get('video_cover', note_info.get('image_list', [''])[0]),
    #             "type": MediaType.VIDEO if is_video else MediaType.IMAGE
    #         }
            
    #         # 处理视频特有信息
    #         if is_video:
    #             media_info.update({
    #                 "video_url": note_info.get('video_addr', ''),
    #                 "duration": 0,  # 小红书API没有提供视频时长
    #                 "width": 0,     # 小红书API没有提供视频宽度
    #                 "height": 0     # 小红书API没有提供视频高度
    #             })
            
    #         # 构造统计数据
    #         statistics = {
    #             "like_count": self._parse_count_string(note_info.get('liked_count', '0')),
    #             "comment_count": self._parse_count_string(note_info.get('comment_count', '0')),
    #             "share_count": self._parse_count_string(note_info.get('share_count', '0')),
    #             "collected_count": self._parse_count_string(note_info.get('collected_count', '0')),
    #             "view_count": 0  # 小红书API没有提供观看数
    #         }
            
    #         # 构造作者信息 - 基础信息
    #         author = {
    #             "id": note_info.get('user_id', ''),
    #             "nickname": note_info.get('nickname', ''),
    #             "avatar": note_info.get('avatar', ''),
    #             "signature": "",  # 笔记API中没有个人签名
    #             "verified": False,  # 笔记API中没有认证信息
    #             "follower_count": 0,  # 笔记API中没有粉丝数
    #             "following_count": 0,  # 笔记API中没有关注数
    #             "notes_count": 0,  # 笔记API中没有笔记数
    #             "location": note_info.get('ip_location', '')
    #         }
            
    #         # 构造标准格式的结果
    #         result = {
    #             "note_id": note_info.get('note_id', ''),
    #             "title": note_info.get('title', ''),
    #             "desc": note_info.get('desc', ''),
    #             "type": MediaType.VIDEO if is_video else MediaType.IMAGE,
    #             "author": author,
    #             "statistics": statistics,
    #             "tags": note_info.get('tags', []),
    #             "media": media_info,
    #             "images": note_info.get('image_list', []),
    #             "original_url": note_info.get('note_url', note_info.get('url', '')),
    #             "create_time": note_info.get('upload_time', ''),
    #             "last_update_time": note_info.get('upload_time', '')  # 小红书API没有更新时间，使用上传时间
    #         }
            
    #         # 转换时间字符串为时间戳（如果有）
    #         if result["create_time"] and isinstance(result["create_time"], str):
    #             result["create_time"] = self._parse_datetime_string(result["create_time"])
            
    #         if result["last_update_time"] and isinstance(result["last_update_time"], str):
    #             result["last_update_time"] = self._parse_datetime_string(result["last_update_time"])
            
    #         return result
    #     except Exception as e:
    #         logger.error(f"转换小红书笔记格式失败: {str(e)}")
    #         # 返回基本信息，避免整个流程失败
    #         return {
    #             "note_id": note_info.get('note_id', ''),
    #             "title": note_info.get('title', ''),
    #             "desc": note_info.get('desc', ''),
    #             # "type": MediaType.UNKNOWN,
    #             "author": {"id": note_info.get('user_id', ''), "nickname": note_info.get('nickname', '')},
    #             "statistics": {},
    #             "tags": [],
    #             "media": {},
    #             "original_url": note_info.get('note_url', '')
    #         }

    def down_media(
        self, 
        task_id: str,
        url: str,
        log_extra: dict
    ):
        logger.info(f"[{task_id}] down_media-开始下载音频: {url}", extra=log_extra)
        
        download_dir = os.path.join(settings.SHARED_TEMP_DIR, f"audio_{int(time.time())}_{task_id[-6:]}")
        os.makedirs(download_dir, exist_ok=True)

        outtmpl = os.path.join(download_dir, "%(title)s.%(ext)s")
        ydl_opts = {
            'outtmpl': outtmpl, 'format': 'bestaudio/best', 'postprocessors': [],
            'quiet': True, 'noplaylist': True, 'geo_bypass': True,
            'socket_timeout': 60, 'retries': 3, 'http_chunk_size': 10 * 1024 * 1024
        }

        media_extract_format = Media_extract_format()
        platform = media_extract_format._identify_platform(url)
        logger.debug(f'current platform: {platform}')
        if platform == "tiktok":
            cookie_path = settings.TIKTOK_COOKIE_FILE
            if os.path.exists(cookie_path):
                ydl_opts["cookiefile"] = cookie_path
            else:
                logger.warning(f"[{task_id}] tiktok平台未找到cookie文件: {cookie_path}", extra=log_extra)

        try:
            logger.debug(f"[{task_id}] 使用的 ydl_opts: {ydl_opts}", extra=log_extra) # 添加这行日志
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise AudioDownloadError("无法提取音频信息 (info is None)")

                downloaded_path = ydl.prepare_filename(info)
                downloaded_title = info.get('title', "downloaded_audio")
                actual_downloaded_path = None

                if os.path.exists(downloaded_path):
                    actual_downloaded_path = downloaded_path
                else:
                    possible_files = [os.path.join(download_dir, f) for f in os.listdir(download_dir)]
                    if possible_files:
                        actual_downloaded_path = max(possible_files, key=os.path.getctime)
                    else:
                        raise AudioDownloadError(f"下载目录为空: {download_dir}")

                logger.info(f"[{task_id}] 音频下载完成: {downloaded_title}, 路径: {actual_downloaded_path}", extra=log_extra)
                return actual_downloaded_path, downloaded_title
        except yt_dlp.utils.DownloadError as e:
            error_msg = f"[{task_id}] 下载音频失败 (yt-dlp DownloadError): {str(e)}"
            logger.error(error_msg, exc_info=True, extra=log_extra)
            raise AudioDownloadError(error_msg) from e
        except Exception as e:
            error_msg = f"[{task_id}] 下载音频时出现未知异常: {type(e).__name__} - {str(e)}"
            logger.error(error_msg, exc_info=True, extra=log_extra)


    def get_transcribed_text(
        self, 
        media_url_to_download:str, 
        platform:str ,
        original_url: str,
        audio_path: str, 
        trace_id: str
    ):
        script_service_sync = ScriptService_Sync()
        result = script_service_sync.transcribe_audio_sync(
            media_url_to_download=media_url_to_download,
            platform=platform,  # 或根据实际平台传参
            original_url=original_url,
            audio_path=audio_path,
            trace_id=trace_id
        )

        return result


    def test_full(self, test_url:str,get_content:bool=True):
        # yt_sync_service = YtDLP_Service_Sync()

        # 测试用的 Bilibili 视频链接 (请替换为有效的链接)
        # test_url = "https://www.bilibili.com/video/BV1..." # 替换这里
        # 调用方法获取信息

        task_id = "test_full"
        log_extra = {
            
        }

        video_info = self.get_basic_info(task_id,test_url,log_extra)

        # def transcribe_audio_sync(self, media_url_to_download:str, platform:str ,original_url: str,audio_path: str, trace_id: str) -> str:
        if get_content:
            actual_downloaded_path, downloaded_title = self.down_media(task_id,video_info.get("media").get("video_url"),log_extra)

            content = self.get_transcribed_text(
                media_url_to_download = test_url,
                platform=video_info.get("platform"),
                original_url=test_url,
                audio_path=actual_downloaded_path,
                trace_id=task_id)

            content_text = content.get("text")
            video_info["content"] = content_text

            PROMPTS = {
                "core": "请你化身**顶尖爆款视频策划人**，以制造刷屏级内容的敏锐嗅觉，审视并提炼出我给你文字中最具冲击力、最能引发用户共鸣和传播的核心观点/价值点。请用简洁精炼的语言，分点列出，并简要阐述每个观点**为何具备成为爆款的潜质**（例如：情感触发点、争议性、实用价值、新奇度、反差感等）。给你的文字是：",
                "formula": "请你扮演一位**深谙传播之道的爆款视频操盘手**，对我给你的文字进行深度解剖，提炼总结出其中可被复用、可迁移的**“爆款密码”或“增长范式”**。请清晰阐述这个“范式”的关键组成部分（如：钩子设计、情绪曲线、价值点呈现节奏、互动引导策略、记忆点打造技巧等），并说明**如何将其巧妙应用于其他内容的创作中**，以显著提升引爆流行、实现增长的可能性。给你的文字是：",
                "copywriting": """请你以**深谙小红书平台特性与用户心理的资深内容运营专家**身份，围绕我给你的文字，创作一篇**至少100字**、**极具“网感”和“种草力”**的小红书爆款笔记文案。要求：
1.  **开头3秒吸睛**，瞬间抓住用户注意力。
2.  **语言生动、场景化**，多使用**emoji**表情符号，营造沉浸式体验。
3.  **价值点清晰、痛点共鸣**，巧妙植入核心信息。
4.  **包含3-5个相关热门#话题标签#**，提升曝光潜力。
5.  **结尾设置巧妙的互动引导**（如提问、投票、求助、号召行动等）。
请产出**2-3个不同风格或侧重点的文案版本**，供我挑选优化。,给你的文字是：""",
                "golden3s": """请你作为**精通“黄金三秒”法则、能瞬间点燃用户好奇心的爆款视频大师**，针对我给你的文字，构思**3-5个**能够在**视频开篇3秒内**就**牢牢锁住观众眼球、激发强烈观看欲望**的**创意开场方案**。请具体描述每个方案的：
* **核心悬念/钩子**
并简要阐述每个方案**为何能有效抓住注意力并驱动用户继续观看**。我给你的文字是：
                """
            }

            openai_service = OpenRouterService()
            for key in ["core", "formula", "copywriting", "golden3s"]:
                role = PROMPTS[key]
                ai_result = openai_service.get_ai_assistant_text(role, task_id, content_text, log_extra)
                # 可根据 key 分类处理 ai_result

            print(f'ai_assitent is {ai_result}')

        return video_info








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

#     script_service_sync = ScriptService_Sync()
#     content = script_service_sync.transcribe_audio_sync(
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

#     # 可以在这里添加更多测试用例，包括无效链接、超时的场景等
#     # invalid_url = "https://invalid-url"
#     # print(f"\n测试无效 URL: {invalid_url}")
#     # bili_sync_service.get_basic_info(invalid_url)