import re
from typing import Dict, Any, Optional, Tuple, Union, List
from datetime import datetime

from celery.platforms import _platform

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.services.business import open_router_service
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.core.cache import cache_result
# from bot_api_v1.app.services.business.douyin_service import DouyinService, DouyinError
from bot_api_v1.app.services.business.tiktok_service import TikTokService, TikTokError
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
from bot_api_v1.app.services.business.xhs_service import XHSService
from bot_api_v1.app.services.business.kuaishou_service import KuaishouService
from bot_api_v1.app.constants.media_info import MediaPlatform
from bot_api_v1.app.utils.media_extrat_format import Media_extract_format
from bot_api_v1.app.services.business.yt_dlp_service import YtDLP_Service_Sync
from bot_api_v1.app.services.business.open_router_service import OpenRouterService
from bot_api_v1.app.core.cache import async_cache_result


import urllib
import json
import ast # 用于解析Python字面量格式的字符串

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
        media_extrat_format = Media_extract_format()
        return media_extrat_format._identify_platform(url)
    
    @gate_keeper()
    @log_service_call(method_type="media", tollgate="10-2")
    @cache_result(expire_seconds=600, prefix="media_extract")
    async def extract_media_content(self, url: str, extract_text: bool = True, include_comments: bool = False, cal_points: bool = True) -> Dict[str, Any]:
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
                return await self._process_douyin(url, extract_text, include_comments,cal_points)
            elif platform == MediaPlatform.XIAOHONGSHU:
                return await self._process_xiaohongshu(url, extract_text, include_comments,cal_points)
            elif platform == MediaPlatform.KUAISHOU:     
                return await self._process_kuaishou(url, extract_text, include_comments, cal_points)
            elif platform == MediaPlatform.YOUTUBE or platform == MediaPlatform.TIKTOK or platform == MediaPlatform.INSTAGRAM or platform == MediaPlatform.TWITTER or platform == MediaPlatform.BILIBILI:
                return await self._process_bl(url, extract_text, include_comments, cal_points)

            if media_data is None: # 检查返回值
                raise TikTokError(f"未能获取{platform}基础信息 (内部方法返回 None)")
            else:
                raise MediaError(f"不支持的媒体平台: {url}")

        except Exception as e:
            error_msg = f"处理媒体内容时出错: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            if isinstance(e, (TikTokError, MediaError)):
                raise MediaError(error_msg) from e
            raise MediaError(f"未知错误: {error_msg}") from e
    
    async def _process_kuaishou(self, url: str, extract_text: bool, include_comments: bool, cal_points: bool = True) -> Dict[str, Any]:
        trace_key = request_ctx.get_trace_key()
        log_extra = {"request_id": trace_key}
        ks_service = KuaishouService()
        basic_info_result = await ks_service.async_get_video_info(trace_key, url, log_extra)

        # media_data = basic_info_result.get("data")

        return basic_info_result

    async def _process_bl(self, url: str, extract_text: bool, include_comments: bool, cal_points: bool = True) -> Dict[str, Any]:
        trace_key = request_ctx.get_trace_key()
        log_extra = {"request_id": trace_key}
        yt_dlp_service = YtDLP_Service_Sync()
        basic_info_result = await yt_dlp_service.async_get_basic_info(trace_key, url, log_extra)

        # media_data = basic_info_result.get("data")

        return basic_info_result
    async def _process_douyin(self, url: str, extract_text: bool, include_comments: bool, cal_points: bool = True) -> Dict[str, Any]:
        """处理抖音内容"""
        trace_key = request_ctx.get_trace_key()
        logger.info_to_db(f"处理抖音内容: {url}", extra={"request_id": trace_key})
        
        # 使用 async with 语句正确初始化 TikTokService
        async with self.tiktok_service as service:
            # 调用抖音服务获取视频信息
            video_info = await service.get_video_info(url,extract_text=extract_text,cal_points=cal_points)        

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
    
    async def _process_xiaohongshu(self, url: str, extract_text: bool, include_comments: bool, cal_points: bool = True) -> Dict[str, Any]:
        """处理小红书内容"""
        trace_key = request_ctx.get_trace_key()
        logger.info_to_db(f"处理小红书内容: {url}", extra={"request_id": trace_key})
        
        try:
            # 调用XHSService获取小红书笔记信息
            note_info = await self.xhs_service.get_note_info(url, extract_text=extract_text,cal_points=cal_points)
            
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
            
    @staticmethod
    def convert_to_standard_format(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        将各种格式的媒体数据转换为标准格式，适用于API响应和Celery任务结果
        
        Args:
            data: 原始媒体数据
            
        Returns:
            Dict: 标准格式的媒体数据
        """
        # 判断数据来源平台
        platform = data.get("platform", "unknown")
        
        # 如果数据中有note_id，可能是小红书数据
        if "note_id" in data and platform == "unknown":
            platform = MediaPlatform.XIAOHONGSHU
        
        # 如果数据中有id但没有note_id，可能是抖音数据
        elif "id" in data and "note_id" not in data and platform == "unknown":
            platform = MediaPlatform.DOUYIN
        
        if platform == MediaPlatform.XIAOHONGSHU:
            # 小红书数据结构转换
            result = {
                "platform": MediaPlatform.XIAOHONGSHU,
                "video_id": data.get("note_id", ""),
                "original_url": data.get("original_url", ""),
                "title": data.get("title", ""),
                "description": data.get("desc", ""),
                "content": data.get("content", "") or data.get("transcribed_text", ""),
                "tags": data.get("tags", []),
                
                "author": {
                    "id": data.get("author", {}).get("id", ""),
                    "sec_uid": data.get("author", {}).get("id", ""),  # 使用id作为sec_uid
                    "nickname": data.get("author", {}).get("nickname", ""),
                    "avatar": data.get("author", {}).get("avatar", ""),
                    "signature": data.get("author", {}).get("signature", ""),
                    "verified": data.get("author", {}).get("verified", False),
                    "follower_count": data.get("author", {}).get("follower_count", 0),
                    "following_count": data.get("author", {}).get("following_count", 0),
                    "region": data.get("author", {}).get("location", "")
                },
                
                "statistics": {
                    "like_count": data.get("statistics", {}).get("like_count", 0),
                    "comment_count": data.get("statistics", {}).get("comment_count", 0),
                    "share_count": data.get("statistics", {}).get("share_count", 0),
                    "collect_count": data.get("statistics", {}).get("collected_count", 0),
                    "play_count": data.get("statistics", {}).get("view_count", 0)
                },
                
                "media": {
                    "cover_url": data.get("media", {}).get("cover_url", "") or (data.get("images", [""])[0] if data.get("images") else ""),
                    "video_url": data.get("media", {}).get("video_url", ""),
                    "duration": data.get("media", {}).get("duration", 0),
                    "width": data.get("media", {}).get("width", 0),
                    "height": data.get("media", {}).get("height", 0),
                    "quality": "normal"
                }
            }
            
            # 处理时间戳
            create_time = data.get("create_time", 0)
            update_time = data.get("last_update_time", 0)
            
            if create_time:
                try:
                    # 处理秒级和毫秒级时间戳
                    if create_time > 10000000000:  # 毫秒级
                        create_time = create_time / 1000
                    result["publish_time"] = datetime.fromtimestamp(create_time).isoformat()
                except:
                    pass
                    
            if update_time:
                try:
                    # 处理秒级和毫秒级时间戳
                    if update_time > 10000000000:  # 毫秒级
                        update_time = update_time / 1000
                    result["update_time"] = datetime.fromtimestamp(update_time).isoformat()
                except:
                    pass
                
        else:
            # 抖音或其他平台数据结构
            result = {
                "platform": MediaPlatform.DOUYIN,
                "video_id": data.get("id", ""),
                "original_url": data.get("original_url", ""),
                "title": data.get("desc", ""),
                "description": data.get("desc", ""),
                "content": data.get("transcribed_text", ""),
                "tags": [],
                
                "author": {
                    "id": data.get("uid", ""),
                    "sec_uid": data.get("sec_uid", "") or data.get("uid", ""),
                    "nickname": data.get("nickname", ""),
                    "avatar": "",
                    "signature": data.get("signature", ""),
                    "verified": False,
                    "follower_count": 0,
                    "following_count": 0,
                    "region": ""
                },
                
                "statistics": {
                    "like_count": data.get("digg_count", 0),
                    "comment_count": data.get("comment_count", 0),
                    "share_count": data.get("share_count", 0),
                    "collect_count": data.get("collect_count", 0),
                    "play_count": data.get("play_count", 0)
                },
                
                "media": {
                    "cover_url": data.get("origin_cover", ""),
                    "video_url": data.get("downloads", ""),
                    "duration": 0,
                    "width": data.get("width", 0),
                    "height": data.get("height", 0),
                    "quality": "normal"
                }
            }
            
            # 处理时间戳
            create_timestamp = data.get("create_timestamp", 0)
            if create_timestamp:
                try:
                    # 处理秒级和毫秒级时间戳
                    if create_timestamp > 10000000000:  # 毫秒级
                        create_timestamp = create_timestamp / 1000
                    result["publish_time"] = datetime.fromtimestamp(create_timestamp).isoformat()
                    result["update_time"] = None
                except:
                    pass
        
        return result

    async def search_note_by_kword(self, trace_key:str, platform: str, query: str, num: int, sort: str,log_extra: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            logger.info_to_db(f"search_note_by_platform开始搜索小红书内容-{query}", extra=log_extra)
         
            if platform == MediaPlatform.XIAOHONGSHU:
                # 调用异步小红书搜索方法
                xhs_data = await self.xhs_service.async_get_search_some_note(trace_key,platform,query,num,sort)
                
                logger.debug(f"search_note_by_kword---xhs_data---搜索结果: {xhs_data}", extra=log_extra)
                return xhs_data
            # 可扩展其他平台
            else:
                raise MediaError(f"暂不支持的平台: {platform}")
        except Exception as e:
            logger.error(f"搜索小红书内容时出错: {str(e)}", extra=log_extra)


    async def extract_xiaohongshu_data(data_input) -> list:
        """
        从小红书API返回的数据中提取笔记信息。
        :param data_input: JSON字符串，或Python列表/字典。
        :return: 提取后的字典列表。
        """
        items_data = []
        if isinstance(data_input, str):
            try:
                items_data = json.loads(data_input)
            except json.JSONDecodeError:
                try:
                    items_data = ast.literal_eval(data_input)
                except (ValueError, SyntaxError) as e:
                    logger.error(f"extract_xiaohongshu_data: 输入数据字符串解析失败: {e}")
                    return []
        elif isinstance(data_input, list):
            items_data = data_input
        else:
            logger.error("extract_xiaohongshu_data: 输入数据必须是JSON字符串或Python列表。实际类型: %s", type(data_input))
            return []

        if not isinstance(items_data, list):
            logger.error(f"extract_xiaohongshu_data: 期望顶层数据结构为列表，实际为: {type(items_data)}")
            return []

        extracted_list = []
        for item in items_data:
            if not isinstance(item, dict):
                logger.warning(f"extract_xiaohongshu_data: 跳过非字典类型元素: {item}")
                continue
            note_card = item.get('note_card') or {}
            if not isinstance(note_card, dict):
                logger.warning(f"extract_xiaohongshu_data: item ID '{item.get('id')}' 的 note_card 不是字典类型，已跳过。")
                note_card = {}
            user_info = note_card.get('user') or {}
            if not isinstance(user_info, dict):
                user_info = {}
            interact_info = note_card.get('interact_info') or {}
            if not isinstance(interact_info, dict):
                interact_info = {}
            item_id = item.get('id', '未知ID')
            xsec_token = item.get('xsec_token', '未知ID')
            note_url = f"https://www.xiaohongshu.com/explore/{item_id}?xsec_token={xsec_token}&xsec_source=" if item_id != '未知ID' else '未知链接'
            def safe_int(val):
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return 0
            likes_count = safe_int(interact_info.get('liked_count', 0))
            collected_count = safe_int(interact_info.get('collected_count', 0))
            comment_count = safe_int(interact_info.get('comment_count', 0))
            shared_count = safe_int(interact_info.get('shared_count', 0))
            extracted_item = {
                # 'id': item_id,
                '标题': note_card.get('display_title', '无标题'),
                '作者': user_info.get('nick_name') or user_info.get('nickname', '未知作者'),
                '分享数': shared_count,
                '点赞数': likes_count,
                '收藏数': collected_count,
                '评论数': comment_count,
                '笔记链接': note_url
            }
            extracted_list.append(extracted_item)

        if extracted_list:
            logger.debug(f'extracted_list is {json.dumps(extracted_list)}')
        
        return extracted_list

    
    async def extract_xiaohongshu_data_str(data_input) -> str:
        """
        将小红书数据整理为可阅读字符串。
        :param data_input: JSON字符串或Python列表/字典。
        :return: 格式化后的字符串。
        """
        x_list = await extract_xiaohongshu_data(data_input)
        if not x_list:
            return ""

        lines = []
        for idx, item in enumerate(x_list, 1):
            line = (
                f"标题：{item.get('标题', '')}\n"
                f"作者：{item.get('作者', '')}\n"
                f"点赞数：{item.get('点赞数', 0)}  收藏数：{item.get('收藏数', 0)}  评论数：{item.get('评论数', 0)}  分享数：{item.get('分享数（或作为播放参考）', 0)}\n"
                f"笔记链接：{item.get('笔记链接', '')}\n"
            )
            lines.append(line)
        return "\n".join(lines)


    @async_cache_result(expire_seconds=600, prefix="media-service")
    async def async_get_user_info(self, platform: str, user_id: str,log_extra: Dict[str, Any]) -> Dict[str, Any]:
        try:
            logger.info_to_db(f"获取用户信息 -async_get_user_info，platform-{platform},user_id is {user_id}", extra=log_extra)
         
            data = {}
            if platform == MediaPlatform.XIAOHONGSHU:
                xhs_data = await self.xhs_service.async_get_user_info(user_id,log_extra)
                if xhs_data.get('success'):
                    logger.debug(f"async_get_user_info---xhs_data---搜索结果: {xhs_data}", extra=log_extra)
                    data = xhs_data.get('data')
                    data = json.dumps(data)
                    logger.debug(f"async_get_user_info---data---搜索结果: {data}", extra=log_extra)

                    return data

                data = xhs_data
                logger.debug(f"async_get_user_info---xhs_data---搜索结果: {json.dumps(data)}", extra=log_extra)
                return data
            # 可扩展其他平台
            else:
                raise MediaError(f"暂不支持的平台: {platform}")
        except Exception as e:
            logger.error(f"获取用户信息 -async_get_user_info: {str(e)}", extra=log_extra)


    @async_cache_result(expire_seconds=600, prefix="media-service")
    async def async_get_user_post_note(self, platform: str, user_url: str,log_extra: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            logger.info_to_db(f"获取用户信息 -async_get_user_post_note-{platform},user_url is {user_url}", extra=log_extra)
         
            if platform == MediaPlatform.XIAOHONGSHU:
                # 调用异步小红书搜索方法
                xhs_data = await self.xhs_service.async_get_user_post_note(user_url,log_extra)
                
                logger.debug(f"async_get_user_post_note---xhs_data---搜索结果: {xhs_data}", extra=log_extra)
                return xhs_data
            # 可扩展其他平台
            else:
                raise MediaError(f"暂不支持的平台: {platform}")
        except Exception as e:
            logger.error(f"获取用户信息 -async_get_user_post_note: {str(e)}", extra=log_extra)

    @async_cache_result(expire_seconds=60, prefix="media-service")
    async def async_get_user_full_info(self, platform: MediaPlatform, user_url: str,log_extra: Dict[str, Any]) -> Dict[str,Any]:
        urlParse = urllib.parse.urlparse(user_url)
        user_id = urlParse.path.split("/")[-1]
        
        if platform == MediaPlatform.XIAOHONGSHU:
            user_info = await self.async_get_user_info(platform, user_id,log_extra)
            note_list = await self.async_get_user_post_note(platform, user_url,log_extra)
        else:
            raise MediaError(f"async_get_user_full_info-暂不支持的平台: {platform}")

        return await self.create_xhs_user_info_schema(user_info,note_list,log_extra)

    
    @async_cache_result(expire_seconds=60, prefix="media-service")
    async def create_xhs_user_info_schema(
        self,
        user_info_raw: Any,  # 可能是JSON字符串或已解析的字典
        note_list_input: List[Dict[str, Any]], # 这是原始的笔记列表数据
        log_extra: Dict[str, Any],
        top_num:int = 3
    ) -> Dict[str, Any]:
        """
        根据原始用户信息和笔记列表，生成一个结构化的用户信息概要。
        """
        logger.debug("create_xhs_user_info_schema: 开始处理用户全量信息。", extra=log_extra)

        # 1. 解析 user_info_raw
        parsed_user_info: Dict[str, Any] = {}
        if isinstance(user_info_raw, str):
            try:
                parsed_user_info = json.loads(user_info_raw)
            except json.JSONDecodeError as e:
                logger.error(f"解析 user_info_raw 字符串失败: {e}", extra=log_extra)
        elif isinstance(user_info_raw, dict):
            parsed_user_info = user_info_raw
        else:
            logger.warning("user_info_raw 既不是字符串也不是字典，user_info 将使用空字典。", extra=log_extra)

        # 2. 提取用户基本信息
        basic_info = parsed_user_info.get('basic_info', {})
        nickname = basic_info.get('nickname', '未知')
        # 性别：1 通常代表男性，0 或 2 代表女性，具体根据小红书定义。这里直接返回值。
        # 你提供的示例 user_info 中 gender: 1, 但 tags 里有 gender-female-v1.png，存在矛盾。
        # 为避免错误解读，这里直接返回API给的数字，或设为"未知"。
        gender_val = basic_info.get('gender')
        gender_str = "未知"
        if gender_val == 1:
            gender_str = "男" # 假设1为男
        elif gender_val == 0 or gender_val == 2: # 假设0或2为女
            gender_str = "女"
        
        signature = basic_info.get('desc', '无签名')

        # 3. 提取互动数据
        interactions = parsed_user_info.get('interactions', [])
        followers_count = 0
        following_count = 0
        total_likes_collections_count = 0 # “获赞与收藏”总数
        for interaction in interactions:
            if isinstance(interaction, dict):
                count_str = interaction.get('count', '0')
                try:
                    count_val = int(count_str)
                except ValueError:
                    count_val = 0
                
                interaction_type = interaction.get('type')
                if interaction_type == 'fans':
                    followers_count = count_val
                elif interaction_type == 'follows':
                    following_count = count_val
                elif interaction_type == 'interaction': # 根据你的示例，这是 "获赞与收藏"
                    total_likes_collections_count = count_val
        
        # 4. 发布笔记数 (基于传入的 note_list_input 长度)
        # 注意：这假设 note_list_input 代表了该用户用于统计的所有相关笔记
        published_notes_count = len(note_list_input) if isinstance(note_list_input, list) else 0

        # 5. 缺失数据的占位符
        new_followers_yesterday = "N/A (数据未提供)"
        new_likes_collections_yesterday = "N/A (数据未提供)" # 对应“获赞与收藏”
        new_posts_yesterday = "N/A (数据未提供)"

        # 6. 获取词云标签 (使用原始笔记列表)
        kwords_data = []
        if hasattr(self, 'get_keywords_for_wordcloud') and isinstance(note_list_input, list) and note_list_input:
            task_id_for_keywords = log_extra.get("request_id", "kwords_task_default")
            kwords_result = await open_router_service.get_keywords_for_wordcloud(
                note_list_input, 
                task_id=task_id_for_keywords, 
                log_extra=log_extra
            )
            if kwords_result.get('success'):
                kwords_data = kwords_result.get('keywords', [])
        
        # 7. 处理发布的笔记列表 (先排序，再提取所需字段)
        # 我们将对所有传入的笔记进行排序和格式化
        sorted_note_list: List[Dict[str, Any]] = []
        if hasattr(self, 'async_get_note_hot_post') and isinstance(note_list_input, list) and note_list_input:
            sorted_note_list = await self.async_get_note_hot_post(
                note_list_input, 
                top_n=len(note_list_input), # 处理所有笔记
                log_extra=log_extra
            )
        elif isinstance(note_list_input, list): # 如果排序方法不存在，则使用原始列表
             sorted_note_list = note_list_input


        published_videos_formatted_list = []
        for note in sorted_note_list:
            if not isinstance(note, dict):
                continue

            interact_info = note.get('interact_info', {})
            if not isinstance(interact_info, dict): interact_info = {} # 安全处理

            try:
                likes = int(interact_info.get('liked_count', 0))
            except (ValueError, TypeError):
                likes = 0
                
            note_id = note.get('note_id', '')
            xsec_token = note.get('xsec_token', '')
            # "视频链接" - 实际上是笔记详情页链接
            video_link = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source=" if note_id else "未知链接"

            published_videos_formatted_list.append({
                "title": note.get('display_title', '无标题'),
                "dig_num": likes,
                "note_link": video_link, # 更改为"笔记链接"更准确
                # "_is_sticky": interact_info.get('sticky', False) # 可选：如果需要在结果中也看到置顶状态
            })

            published_videos_formatted_list = published_videos_formatted_list[:top_num]

        
        # 8. 组装最终结果
        final_schema = {
            "name": nickname,
            "gender": gender_str, # 返回 "男", "女", 或 "未知"
            "desc": signature,
            "fans": followers_count,
            "followings": following_count,
            "digs": total_likes_collections_count, # 根据你的数据来源，这是合并的
            "posts": published_notes_count, # 使用 "笔记" 替代 "视频" 更通用
            "new_fans": new_followers_yesterday,
            "new_digs": new_likes_collections_yesterday,
            "new_posts": new_posts_yesterday,
            "tag": kwords_data, # 这是 get_keywords_for_wordcloud 返回的列表
            "post_list": published_videos_formatted_list # 列表中的笔记已排序
        }
        
        logger.debug(f"create_xhs_user_info_schema --- final_schema ---: {json.dumps(final_schema, ensure_ascii=False, indent=2)}", extra=log_extra)
        return final_schema


    @async_cache_result(expire_seconds=60, prefix="media-service")
    async def async_get_note_hot_post(
        self,
        note_list: List[Dict[str, Any]],
        top_n: int = 10,
        log_extra: Dict[str, Any] = None # 如果需要日志，可以取消注释并传递
    ) -> List[Dict[str, Any]]:
        """
        对笔记列表进行排序：置顶笔记优先，然后在各自组内（置顶/非置顶）按热度指标（如点赞数）降序排列。
        返回热度最高的 top_n 条笔记。
        原始笔记对象中的 'sticky' 标签信息会被保留。

        :param note_list: 包含笔记信息的字典列表。
        :param top_n: 需要返回的热门笔记数量，默认为10。
        :return: 排序后的 top_n 条笔记的列表。
        """
        # if log_extra is None:
        #     log_extra = {}
        # logger.debug(f"async_get_note_hot_post: 开始处理热门笔记 (置顶优先), top_n={top_n}", extra=log_extra)
        logger.debug(f"async_get_note_hot_post: 开始处理热门笔记 (置顶优先), top_n={top_n}")

        if not isinstance(note_list, list) or not note_list:
            # logger.warning("async_get_note_hot_post: note_list 为空或非列表类型。", extra=log_extra)
            logger.debug("async_get_note_hot_post: note_list 为空或非列表类型。")
            return []

        def get_sort_criteria(note: Dict[str, Any]) -> Tuple[bool, int]:
            """
            返回一个用于排序的元组: (是否置顶, 热度分数)。
            Python的sorted函数配合reverse=True时，会先比较元组的第一个元素（True > False），
            如果相同，则比较第二个元素。
            """
            is_sticky = False
            hotness_score = 0
            
            try:
                interact_info = note.get('interact_info')
                if isinstance(interact_info, dict):
                    # 直接获取布尔值sticky状态，如果不存在则默认为False
                    is_sticky = interact_info.get('sticky', False) == True 
                    
                    liked_count_str = interact_info.get('liked_count')
                    if liked_count_str is not None:
                        hotness_score = int(liked_count_str) # 点赞数是字符串，需转为整数
                else:
                    logger.debug(f"笔记 ID {note.get('note_id', '未知')} 缺少 interact_info 字典。", extra=log_extra)

            except (ValueError, TypeError) as e:
                logger.warning(f"无法解析笔记 ID {note.get('note_id', '未知')} 的互动信息或点赞数: {e}", extra=log_extra)
                # print(f"无法解析笔记 ID {note.get('note_id', '未知')} 的互动信息或点赞数: {e}")
                # hotness_score 保持 0, is_sticky 保持 False
            
            return (is_sticky, hotness_score)

        try:
            # 使用 get_sort_criteria 返回的元组进行排序
            # reverse=True:
            # 1. 对于 is_sticky (布尔值): True (置顶) 会排在 False (非置顶) 前面。
            # 2. 对于 hotness_score (整数): 在 is_sticky 相同的情况下，点赞数高的会排在前面。
            sorted_notes = sorted(note_list, key=get_sort_criteria, reverse=True)
        except Exception as e:
            logger.error(f"排序笔记时发生错误: {e}", exc_info=True, extra=log_extra)
            # print(f"排序笔记时发生错误: {e}")
            return []

        logger.debug(f"async_get_note_hot_post: 排序完成 (置顶优先)，获取前 {top_n} 条。", extra=log_extra)
        
        # 返回排序后的前 top_n 条笔记，笔记对象本身没有改变，所以置顶标签信息自然保留
        return sorted_notes[:top_n]


    @async_cache_result(expire_seconds=600,prefix="media_service")
    async def get_user_profile(self, user_url: str, log_extra: Dict[str, Any], retries: Optional[int] = None) -> Dict[str, Any]:
        """根据用户主页地址获取抖音用户信息，自动判断平台"""
        logger.info(f"get_user_profile-开始获取用户主页信息: {user_url}", extra=log_extra)
        platform = self.identify_platform(user_url)
        logger.info(f"识别到平台: {platform}", extra=log_extra)
        if platform != MediaPlatform.DOUYIN:
            logger.error(f"当前仅支持抖音平台，实际为: {platform}", extra=log_extra)
            raise MediaError(f"仅支持抖音平台，实际为: {platform}")
        attempt = 0
        last_exception = None
        while retries is None or attempt < retries:
            try:
                async with self.tiktok_service as service:
                    logger.info(f"调用get_user_profile_by_url方法, attempt={attempt+1}", extra=log_extra)
                    profile = await service.get_user_profile_by_url(user_url, log_extra=log_extra)
                    logger.info(f"成功获取用户主页信息", extra=log_extra)
                    return profile
            except Exception as e:
                last_exception = e
                logger.warning(f"获取用户主页信息失败, attempt={attempt+1}, error: {e}", extra=log_extra)
                attempt += 1
        logger.error(f"多次重试后仍未获取到用户主页信息", extra=log_extra)
        raise MediaError(f"获取抖音用户主页信息失败: {last_exception}")

    
    # @async_cache_result(expire_seconds=600,prefix="media_service")
    async def async_get_comment_by_url(self, video_url: str, log_extra: Dict[str, Any]) -> List[Dict[str, Any]]:
        platform = self.identify_platform(video_url)
        logger.info(f"async_get_comment_by_url-识别平台: {platform}", extra=log_extra)
        try:
            if platform == MediaPlatform.DOUYIN:
                logger.info(f"async_get_comment_by_url-调用抖音评论接口", extra=log_extra)
                async with self.tiktok_service as service:
                    comments = await service.get_all_video_comments(video_url, platform=platform,log_extra=log_extra) 
                result = {
                    "platform": platform,
                    "comments": comments,
                    "status": "success"
                }
            elif platform == MediaPlatform.XIAOHONGSHU:
                logger.info(f"async_get_comment_by_url-调用小红书评论接口", extra=log_extra)
                comments = await self.xhs_service.async_get_note_all_comment(video_url, log_extra)
                result = {
                    "platform": platform,
                    "comments": comments,
                    "status": "success"
                }
            else:
                logger.warning(f"async_get_comment_by_url-暂不支持的平台: {platform}", extra=log_extra)
                result = {
                    "platform": platform,
                    "comments": [],
                    "status": "unsupported",
                    "msg": f"暂不支持的平台: {platform}"
                }
            logger.info(f"async_get_comment_by_url-获取评论成功", extra=log_extra)
            return result
        except Exception as e:
            logger.error(f"async_get_comment_by_url-获取评论失败: {str(e)}", extra=log_extra)
            return {
                "platform": platform,
                "comments": [],
                "status": "error",
                "msg": str(e)
            }