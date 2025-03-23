# src/bot_api_v1/app/services/business/xhs_service.py
from typing import Dict, Any, Optional, Tuple, List
import httpx
import json
import time
import os
import asyncio
import aiofiles
from tikhub import Client
from dotenv import load_dotenv

from bot_api_v1.app.core.cache import cache_result
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
from bot_api_v1.app.services.business.script_service import ScriptService, AudioDownloadError, AudioTranscriptionError

class XHSError(Exception):
    """小红书服务操作过程中出现的错误"""
    pass

class XHSService:
    """小红书服务，提供小红书相关的业务操作"""
    
    def __init__(self, 
                 api_timeout: int = 30,
                 cache_duration: int = 3600):
        """
        初始化小红书服务
        
        Args:
            api_timeout: API请求超时时间(秒)
            cache_duration: 缓存持续时间(秒)
        """
        self.api_timeout = api_timeout
        self.cache_duration = cache_duration
        
        # 从环境变量中获取 API_KEY
        load_dotenv()
        self.api_key = os.getenv("TIKHUB_API_KEY", "4e0aD3t43VorozAD3XPqu0Qo7llWzbLeqpdekG3/r2Yf0W40UuRu6CiRBA==")
        
        # 初始化 TikHub 客户端
        self.client = Client(api_key=self.api_key)
        
        # 初始化 ScriptService 用于音频处理
        self.script_service = ScriptService()
        
        # 下载目录
        self.download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(self.download_dir, exist_ok=True)
    
    @gate_keeper()
    @log_service_call(method_type="xhs", tollgate="10-2")
    @cache_result(expire_seconds=3600)
    async def get_note_info(self, note_url: str, extract_text: bool = False) -> Dict[str, Any]:
        """
        获取小红书笔记信息
        
        Args:
            note_url: 小红书笔记URL
            extract_text: 是否提取文案，默认为False
                
        Returns:
            Dict[str, Any]: 笔记信息，包含标题、作者、描述等
                
        Raises:
            XHSError: 处理过程中出现的错误
        """
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()
        
        logger.info(f"开始获取小红书笔记信息: {note_url}, extract_text={extract_text}", 
                extra={"request_id": trace_key})
        
        try:
            # 调用TikHub SDK获取笔记信息
            note_data = await self.client.XiaohongshuWeb.get_note_info_v2(note_url)
            
            if not note_data or 'data' not in note_data or 'note' not in note_data['data']:
                error_msg = f"未能获取有效的笔记信息，API响应: {json.dumps(note_data, ensure_ascii=False)}"
                logger.error(error_msg, extra={"request_id": trace_key})
                raise XHSError(error_msg)
            
            # 提取关键信息
            note = note_data['data']['note']
            
            # 提取标签
            tags = []
            if 'tag_list' in note and note['tag_list']:
                tags = [tag.get('name', '') for tag in note['tag_list'] if 'name' in tag]
            
            # 构造作者信息
            author = {
                "id": note.get('user', {}).get('user_id', ''),
                "nickname": note.get('user', {}).get('nickname', ''),
                "avatar": note.get('user', {}).get('avatar', ''),
                "signature": note.get('user', {}).get('desc', ''),
                "verified": note.get('user', {}).get('verified', False),
                "follower_count": note.get('user', {}).get('fans_count', 0),
                "following_count": note.get('user', {}).get('follow_count', 0),
                "notes_count": note.get('user', {}).get('notes_count', 0),
                "location": note.get('user', {}).get('location', '')
            }
            
            # 提取统计数据
            statistics = {
                "like_count": note.get('like_count', 0),
                "comment_count": note.get('comment_count', 0),
                "share_count": note.get('share_count', 0),
                "collected_count": note.get('collected_count', 0),
                "view_count": note.get('view_count', 0)
            }
            
            # 提取媒体信息
            media_info = {
                "cover_url": note.get('cover', {}).get('url', ''),
                "type": note.get('type', '')  # 可能的值: 'normal', 'video'
            }
            
            # 处理视频特有信息
            if note.get('type') == 'video' and 'video' in note:
                media_info.update({
                    "video_url": note.get('video', {}).get('url', ''),
                    "duration": note.get('video', {}).get('duration', 0),
                    "width": note.get('video', {}).get('width', 0),
                    "height": note.get('video', {}).get('height', 0)
                })
            
            # 构造图片列表
            images = []
            if 'images' in note and note['images']:
                images = [img.get('url', '') for img in note['images'] if 'url' in img]
            
            # 提取文案（如果需要）
            transcribed_text = None
            if extract_text and note.get('type') == 'video' and note.get('video', {}).get('url'):
                try:
                    video_url = note.get('video', {}).get('url', '')
                    logger.info(f"开始提取视频文案: {note.get('note_id', '')}", extra={"request_id": trace_key})
                    
                    # 下载视频
                    audio_path, audio_title = await self.script_service.download_audio(video_url)
                    
                    # 转写音频
                    transcribed_text = await self.script_service.transcribe_audio(audio_path)
                    
                    logger.info(f"成功提取视频文案", extra={"request_id": trace_key})
                except Exception as e:
                    logger.error(f"提取视频文案失败: {str(e)}", exc_info=True, extra={"request_id": trace_key})
                    transcribed_text = f"提取文案失败: {str(e)}"
            
            # 构造结果
            result = {
                "note_id": note.get('note_id', ''),
                "title": note.get('title', ''),
                "desc": note.get('desc', ''),
                "type": note.get('type', ''),
                "author": author,
                "statistics": statistics,
                "tags": tags,
                "media": media_info,
                "images": images,
                "original_url": note_url,
                "create_time": note.get('create_time', 0),
                "last_update_time": note.get('last_update_time', 0)
            }
            
            # 添加文案内容（如果有）
            if extract_text:
                result["transcribed_text"] = transcribed_text
            
            logger.info(f"成功获取小红书笔记信息: {result['note_id']}", extra={"request_id": trace_key})
            return result
                
        except XHSError:
            # 重新抛出XHSError
            raise
        except Exception as e:
            error_msg = f"获取小红书笔记信息失败: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            raise XHSError(error_msg) from e
    
    @gate_keeper()
    @log_service_call(method_type="xhs", tollgate="10-3")
    @cache_result(expire_seconds=3600)
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        获取小红书用户信息
        
        Args:
            user_id: 小红书用户ID
            
        Returns:
            Dict[str, Any]: 用户信息，包含昵称、关注数、粉丝数等
            
        Raises:
            XHSError: 处理过程中出现的错误
        """
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()
        
        logger.info(f"开始获取小红书用户信息: {user_id}", extra={"request_id": trace_key})
        
        try:
            # 调用TikHub SDK获取用户信息
            user_data = await self.client.XiaoHongShu.fetch_user_info(user_id)
            
            if not user_data or 'data' not in user_data or 'user' not in user_data['data']:
                error_msg = f"未能获取有效的用户信息，API响应: {json.dumps(user_data, ensure_ascii=False)}"
                logger.error(error_msg, extra={"request_id": trace_key})
                raise XHSError(error_msg)
            
            # 提取用户信息
            user = user_data['data']['user']
            
            result = {
                "user_id": user.get('user_id', ''),
                "nickname": user.get('nickname', ''),
                "avatar": user.get('avatar', ''),
                "description": user.get('desc', ''),
                "gender": user.get('gender', 0),
                "location": user.get('location', ''),
                "verified": user.get('verified', False),
                "verified_reason": user.get('verified_reason', ''),
                "statistics": {
                    "following_count": user.get('follow_count', 0),
                    "follower_count": user.get('fans_count', 0),
                    "notes_count": user.get('notes_count', 0),
                    "collected_count": user.get('collected_count', 0),
                    "interaction_count": user.get('interaction_count', 0)
                }
            }
            
            logger.info(f"成功获取小红书用户信息: {result['user_id']}", extra={"request_id": trace_key})
            return result
                
        except Exception as e:
            error_msg = f"获取小红书用户信息失败: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            raise XHSError(error_msg) from e