# src/bot_api_v1/app/services/business/douyin_service.py
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

class DouyinError(Exception):
    """抖音服务操作过程中出现的错误"""
    pass

class DouyinService:
    """抖音服务，提供抖音相关的业务操作"""
    
    def __init__(self, 
                 api_timeout: int = 30,
                 cache_duration: int = 3600):
        """
        初始化抖音服务
        
        Args:
            api_timeout: API请求超时时间(秒)
            cache_duration: 缓存持续时间(秒)
        """
        self.api_timeout = api_timeout
        self.cache_duration = cache_duration
        
        # 从环境变量中获取 API_KEY
        load_dotenv()
        self.api_key = os.getenv("TIKHUB_API_KEY", "4e0aD3t43VorozAD3XPqu0Qo7llWzbLeqpdekG3/r2Yf0W40UuRu6CiRBA==")
        # self.api_key = os.getenv("TIKHUB_API_KEY", "kb8MYVxz60AU+HU1imWLqSU1xCoQ0biDsYp3/TzLi1ZzzmU1c95h6g6pUw==")
        # self.api_key = os.getenv("TIKHUB_API_KEY", "kIY3FmRG+UsN4RQj6Ea8pFoBhBQOqqWHlqhXy2nEuU8S7A4LccFj1AC4Pg==")


        # 初始化 TikHub 客户端
        self.client = Client(api_key=self.api_key)
        
        # 下载目录
        self.download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(self.download_dir, exist_ok=True)
    
    @gate_keeper()
    @log_service_call(method_type="douyin", tollgate="10-2")
    @cache_result(expire_seconds=60)
    async def get_video_info(self, video_url: str, extract_text: bool = False) -> Dict[str, Any]:
        """
        获取抖音视频信息，可选择是否同时提取视频文案
        
        Args:
            video_url: 抖音视频URL
            extract_text: 是否提取视频文案，默认为False
                
        Returns:
            Dict[str, Any]: 视频信息，包含标题、作者、描述等，
                        如果extract_text=True，则包含转写的文本内容
                
        Raises:
            DouyinError: 处理过程中出现的错误
        """
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()
        
        logger.info(f"douyin-get_video_info-开始获取抖音视频信息: {video_url}, extract_text={extract_text}", 
                extra={"request_id": trace_key})
        
        try:
            # 调用TikHub SDK获取视频信息
            # video_data = await self.client.DouyinAppV3.fetch_one_video_by_share_url('https://v.douyin.com/FyG7GEh6Zm8/')
            # video_data = await self.client.DouyinAppV3.fetch_one_video('7454208045808225595')
            video_data = await self.client.DouyinAppV3.fetch_one_video_by_share_url(video_url)
            # video_data = await self.client.DouyinAppV3.fetch_one_video_by_share_url('https://v.douyin.com/i53yJjA3/')


            # logger.info(f"douyin-get_video_info-抖音视频信息获取成功: {video_data}, extract_text={extract_text}", 
            #         extra={"request_id": trace_key})
            
            
            if not video_data or 'data' not in video_data or 'aweme_detail' not in video_data['data']:
                error_msg = f"未能获取有效的视频信息，API响应: {json.dumps(video_data, ensure_ascii=False)}"
                logger.error(error_msg, extra={"request_id": trace_key})
                raise DouyinError(error_msg)
            
            # 提取关键信息
            aweme_detail = video_data['data']['aweme_detail']
            
            # 获取视频播放地址
            play_addr = None
            if 'video' in aweme_detail and 'play_addr_265' in aweme_detail['video']:
                play_addr = aweme_detail['video']['play_addr_265']['url_list'][0]
            elif 'video' in aweme_detail and 'play_addr' in aweme_detail['video']:
                play_addr = aweme_detail['video']['play_addr']['url_list'][0]
            
            if not play_addr:
                raise DouyinError("无法获取视频播放地址")
            
            # 提取视频信息
            result = {
                "aweme_id": aweme_detail.get('aweme_id', ''),
                "desc": aweme_detail.get('desc', ''),
                "create_time": aweme_detail.get('create_time', 0),
                "author": {
                    "uid": aweme_detail.get('author', {}).get('uid', ''),
                    "sec_uid": aweme_detail.get('author', {}).get('sec_uid', ''),
                    "short_id": aweme_detail.get('author', {}).get('short_id', ''),
                    "nickname": aweme_detail.get('author', {}).get('nickname', ''),
                    "signature": aweme_detail.get('author', {}).get('signature', ''),
                    "avatar": aweme_detail.get('author', {}).get('avatar_thumb', {}).get('url_list', [''])[0],
                    "total_favorited": aweme_detail.get('author', {}).get('total_favorited', 0),
                    "aweme_count": aweme_detail.get('author', {}).get('aweme_count', 0),
                    "favoriting_count": aweme_detail.get('author', {}).get('favoriting_count', 0),
                    "is_verified": aweme_detail.get('author', {}).get('is_verified', False),
                    "verification_type": aweme_detail.get('author', {}).get('verification_type', 0),
                    "region": aweme_detail.get('author', {}).get('region', '')
                },
                "statistics": {
                    "comment_count": aweme_detail.get('statistics', {}).get('comment_count', 0),
                    "digg_count": aweme_detail.get('statistics', {}).get('digg_count', 0),
                    "share_count": aweme_detail.get('statistics', {}).get('share_count', 0),
                    "collect_count": aweme_detail.get('statistics', {}).get('collect_count', 0),
                    "play_count": aweme_detail.get('statistics', {}).get('play_count', 0)
                },
                "video_url": play_addr,
                "cover_url": aweme_detail.get('video', {}).get('cover', {}).get('url_list', [''])[0],
                "duration": aweme_detail.get('video', {}).get('duration', 0) // 1000,  # 毫秒转秒
                "original_url": video_url
            }
            
            # 如果需要提取文案，进行额外处理
            if extract_text and play_addr:
                logger.info(f"开始提取视频文案: {result['aweme_id']}", extra={"request_id": trace_key})
                
                try:
                    # 创建临时目录，使用视频ID作为前缀，减少冲突
                    temp_dir = os.path.join(self.download_dir, f"{result['aweme_id']}_{int(time.time())}")
                    os.makedirs(temp_dir, exist_ok=True)
                    
                    # 下载视频
                    video_path = os.path.join(temp_dir, f"{result['aweme_id']}.mp4")
                    
                    # 下载视频文件
                    async with httpx.AsyncClient(timeout=self.api_timeout) as client:
                        response = await client.get(play_addr)
                        response.raise_for_status()
                        
                        # 保存视频文件
                        async with aiofiles.open(video_path, "wb") as file:
                            await file.write(response.content)
                    
                    # 检查文件是否成功下载
                    if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
                        raise DouyinError("视频下载失败或文件为空")
                        
                    # 提取音频
                    audio_path = os.path.join(temp_dir, f"{result['aweme_id']}.mp3")
                    
                    # 使用FFmpeg提取音频
                    import subprocess
                    cmd = f"ffmpeg -i {video_path} -q:a 0 -map a {audio_path} -y"
                    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = process.communicate()
                    
                    if process.returncode != 0:
                        stderr_msg = stderr.decode('utf-8', errors='replace')
                        logger.error(f"提取音频失败: {stderr_msg}", extra={"request_id": trace_key})
                        result["transcribed_text"] = "无法提取音频"
                    else:
                        # 检查音频文件是否存在
                        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                            raise DouyinError("音频提取失败或文件为空")
                            
                        # 使用Whisper转写音频
                        from bot_api_v1.app.services.business.script_service import ScriptService
                        script_service = ScriptService()
                        
                        # 转写音频
                        transcribed_text = await script_service.transcribe_audio(audio_path)
                        result["transcribed_text"] = transcribed_text
                        
                        logger.info(f"成功提取视频文案", extra={"request_id": trace_key})
                    
                    # 清理临时文件
                    try:
                        if os.path.exists(video_path):
                            os.remove(video_path)
                        if os.path.exists(audio_path):
                            os.remove(audio_path)
                        os.rmdir(temp_dir)
                    except Exception as e:
                        logger.warning(f"清理临时文件失败: {str(e)}", extra={"request_id": trace_key})
                
                except Exception as e:
                    logger.error(f"提取视频文案失败: {str(e)}", exc_info=True, extra={"request_id": trace_key})
                    result["transcribed_text"] = f"提取文案失败: {str(e)}"
            
            logger.info(f"成功获取抖音视频信息: {result['aweme_id']}", extra={"request_id": trace_key})
            return result
                
        except DouyinError:
            # 重新抛出DouyinError
            raise
        except Exception as e:
            error_msg = f"获取抖音视频信息失败: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            raise DouyinError(error_msg) from e
    
    @gate_keeper()
    @log_service_call(method_type="douyin", tollgate="10-3")
    @cache_result(expire_seconds=60)
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        获取抖音用户信息
        
        Args:
            user_id: 抖音用户ID或sec_uid
            
        Returns:
            Dict[str, Any]: 用户信息，包含昵称、关注数、粉丝数等
            
        Raises:
            DouyinError: 处理过程中出现的错误
        """
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()
        
        logger.info(f"douyin-get_user_info-开始获取抖音用户信息: {user_id}", extra={"request_id": trace_key})
        
        try:
            # 调用TikHub SDK获取用户信息
            user_data = await self.client.DouyinAppV3.handler_user_profile(sec_user_id=user_id)
            print(f'user_data: {user_data}')

            if not user_data or 'data' not in user_data or 'user' not in user_data['data']:
                error_msg = f"未能获取有效的用户信息，API响应: {json.dumps(user_data, ensure_ascii=False)}"
                logger.error(error_msg, extra={"request_id": trace_key})
                raise DouyinError(error_msg)
            
            # 提取用户信息
            user = user_data['data']['user']
            
            result = {
                "uid": user.get('uid', ''),
                "short_id": user.get('short_id', ''),
                "sec_uid": user.get('sec_uid', ''),
                "nickname": user.get('nickname', ''),
                "signature": user.get('signature', ''),
                "avatar": user.get('avatar_larger', {}).get('url_list', [''])[0] if user.get('avatar_larger') else '',
                "verified": user.get('custom_verify', '') != '',
                "custom_verify": user.get('custom_verify', ''),
                "statistics": {
                    "following_count": user.get('following_count', 0),
                    "follower_count": user.get('follower_count', 0),
                    "total_favorited": user.get('total_favorited', 0),
                    "aweme_count": user.get('aweme_count', 0)
                },
                "region": user.get('region', ''),
                "birthday": user.get('birthday', ''),
                "is_enterprise": user.get('is_enterprise', False)
            }
            
            logger.info(f"成功获取抖音用户信息: {result['uid']}", extra={"request_id": trace_key})
            return result
                
        except Exception as e:
            error_msg = f"获取抖音用户信息失败: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            raise DouyinError(error_msg) from e
    
    async def _download_video(self, video_info: dict, play_addr: str) -> Optional[str]:
        """
        下载抖音视频
        
        Args:
            video_info: 视频信息
            play_addr: 视频播放地址
            
        Returns:
            Optional[str]: 下载后的文件路径，失败则返回None
        """
        trace_key = request_ctx.get_trace_key()
        
        try:
            aweme_id = video_info['data']['aweme_detail']['aweme_id']
            file_name = os.path.join(self.download_dir, f"{aweme_id}.mp4")
            
            # 请求文件并下载
            async with httpx.AsyncClient(timeout=self.api_timeout) as http_client:
                response = await http_client.get(play_addr)
                response.raise_for_status()
            
            # 保存文件
            async with aiofiles.open(file_name, "wb") as file:
                await file.write(response.content)
            
            # 验证文件下载成功
            if not os.path.exists(file_name) or os.path.getsize(file_name) == 0:
                logger.error(f"视频下载失败或文件为空: {file_name}", extra={"request_id": trace_key})
                return None
                
            return file_name
            
        except Exception as e:
            logger.error(f"下载视频失败: {str(e)}", exc_info=True, extra={"request_id": trace_key})
            return None