# src/bot_api_v1/app/services/business/tiktok_service.py
from typing import Dict, Any, Optional, List
import os
import sys
import importlib.util
import time
import json
import asyncio
import aiofiles
import httpx
import subprocess
from pathlib import Path

from bot_api_v1.app.core.cache import async_cache_result, cache_result
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.utils.decorators.log_service_call import F, log_service_call
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
from bot_api_v1.app.services.business.script_service import ScriptService
import tempfile  # 添加缺失的导入

# 定义常量
class NoteType:
    VIDEO = "视频"
    IMAGE = "图文"
    UNKNOWN = "unknown"

class MediaType:
    VIDEO = "Video"
    IMAGE = "image"
    UNKNOWN = "unknown"


class TikTokError(Exception):
    """Base exception for TikTok service errors"""
    pass


class InitializationError(TikTokError):
    """Raised when the service fails to initialize"""
    pass


class VideoFetchError(TikTokError):
    """Raised when video information cannot be fetched"""
    pass


class UserFetchError(TikTokError):
    """Raised when user information cannot be fetched"""
    pass



# 添加缺失的异常类定义
class AudioTranscriptionError(TikTokError):
    """Raised when audio transcription fails"""
    pass

class AudioDownloadError(TikTokError):
    """Raised when audio download fails"""
    pass

class TikTokService:
    """
    Production-ready service for interacting with TikTok/Douyin content.
    
    This service provides a clean API to:
    - Fetch video metadata
    - Fetch user profile information
    - Download videos (planned feature)
    
    All operations are performed asynchronously and with proper error handling.
    """
    
    # Class constants
    DEFAULT_TIMEOUT = 30  # seconds
    MAX_RETRIES = 3
    
    def __init__(
        self, 
        cookie: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        debug: bool = False
    ):
        """
        Initialize the TikTok service.
        
        Args:
            cookie: TikTok/Douyin cookie string (optional)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts for failed requests
            debug: Enable debug logging
        
        The service must be used as an async context manager:
        ```
        async with TikTokService() as service:
            info = await service.get_video_info(url)
        ```
        """
        # Set up logging level based on debug flag
        # if debug:
        #     logger.setLevel(logging.DEBUG)
        
        self.cookie = cookie
        self.timeout = timeout
        self.max_retries = max_retries
        
        # 获取项目根目录路径
        current_dir = Path(__file__).resolve().parent
        project_root = current_dir.parents[4]  # bot-api-v1 项目根目录
        self.tiktok_lib_path = project_root / "src" / "bot_api_v1" / "libs" / "tiktok_downloader"
        
        # These will be initialized in __aenter__
        self.console = None
        self.settings = None
        self.cookie_object = None
        self.parameters = None

        self.script_service = ScriptService()
        
        # Import required modules only when actually needed
        self._setup_imports()
    
    
    def _setup_imports(self) -> None:
        """
        Set up the necessary imports from the TikTok downloader library.
        Handles path configuration and imports by adding the submodule root to sys.path.

        Raises:
            ImportError: If required modules cannot be imported
        """
        try:
            # 使用配置中提供的子模块路径
            tiktok_root = Path(self.tiktok_lib_path) # 子模块根目录

            # 检查子模块路径是否存在
            if not tiktok_root.is_dir():
                logger.error(f"TikTok downloader path not found: {tiktok_root}")
                # 可能是子模块未初始化，提示用户
                raise ImportError(f"TikTok downloader library not found at {tiktok_root}. Did you run 'git submodule update --init --recursive'?")

            # --- 新策略：将子模块的根目录添加到 Python 搜索路径 (sys.path) ---
            if str(tiktok_root) not in sys.path:
                sys.path.insert(0, str(tiktok_root))
                logger.debug(f"Added submodule root {tiktok_root} to Python path")

            # --- 处理工作目录更改 (存在风险，但与新 sys.path 策略一致) ---
            self._original_dir = os.getcwd()
            # 警告：os.chdir 更改全局状态，在并发或库代码中存在风险。
            # 只有在确认 tiktok_downloader 库严格要求在其根目录运行时才应保留。
            if os.getcwd() != str(tiktok_root):
                os.chdir(str(tiktok_root))
                logger.debug(f"Changed working directory to {tiktok_root} (Required by submodule?)")
            # --- 工作目录更改结束 ---

            # # --- 正确的导入语句 (基于子模块根目录在 sys.path 中) ---
            # # 现在需要从 src 开始导入
            # from src.config import Settings, Parameter
            # from src.custom import PROJECT_ROOT # 假设 PROJECT_ROOT 在 src/custom/__init__.py 或 src/custom.py 中
            # from src.tools import ColorfulConsole
            # from src.module import Cookie
            # from src.interface import Detail, User
            # from src.link import Extractor
            # from src.extract import Extractor as DataExtractor # 别名保持不变
            # from src.record import BaseLogger

            # 从子模块的 src 目录导入所需组件
            from src.config import Settings, Parameter
            from src.custom import PROJECT_ROOT # 这是子模块内部的 PROJECT_ROOT
            from src.tools import ColorfulConsole
            from src.module import Cookie
            from src.interface import Detail, User, Comment
            from src.interface.detail_tiktok import DetailTikTok # TikTok 视频详情接口
            from src.interface.info_tiktok import InfoTikTok # TikTok 用户简略信息接口 (替代User)
            from src.interface.comment_tiktok import CommentTikTok
            from src.link import Extractor, ExtractorTikTok
            from src.extract import Extractor as DataExtractor 
            from src.record import BaseLogger

            self._imports = {
                "Settings": Settings,
                "Parameter": Parameter,
                "PROJECT_ROOT": PROJECT_ROOT, # 子模块的 PROJECT_ROOT
                "ColorfulConsole": ColorfulConsole,
                "Cookie": Cookie,
                "Detail": Detail, # 抖音视频详情
                "DetailTikTok": DetailTikTok, # TikTok 视频详情
                "User": User, # 抖音用户信息
                "InfoTikTok": InfoTikTok, # TikTok 用户信息 (通常 secUid + uniqueId 可获取)
                "Comment": Comment,
                "CommentTikTok": CommentTikTok,
                "Extractor": Extractor,
                "ExtractorTikTok": ExtractorTikTok,
                "DataExtractor": DataExtractor,
                "BaseLogger": BaseLogger
            }

            logger.debug("成功导入 TikTok Downloader 子模块的所需组件。")
        except ImportError as e:
            # 打印更详细的错误追踪信息，帮助调试是哪个导入失败
            logger.error(f"Failed to import required modules: {str(e)}", exc_info=True)
            if hasattr(self, '_original_dir') and os.getcwd() != self._original_dir:
                try:
                    os.chdir(self._original_dir)
                    logger.debug(f"Restored working directory to {self._original_dir} after import error.")
                except Exception as chdir_err:
                    logger.error(f"Failed to restore working directory after import error: {chdir_err}")
            raise ImportError(f"Could not import TikTok downloader modules (using root path {tiktok_root}): {str(e)}") from e
        except Exception as e:
             logger.error(f"An unexpected error occurred during TikTok downloader import setup: {str(e)}", exc_info=True)
             if hasattr(self, '_original_dir') and os.getcwd() != self._original_dir:
                 try:
                     os.chdir(self._original_dir)
                     logger.debug(f"Restored working directory to {self._original_dir} after unexpected error.")
                 except Exception as chdir_err:
                     logger.error(f"Failed to restore working directory after unexpected error: {chdir_err}")
             raise InitializationError(f"Setup failed for TikTok downloader: {str(e)}") from e
             
    
    async def __aenter__(self) -> 'TikTokService':
        """
        Initialize the service when entering the async context.
        
        Returns:
            The initialized TikTok service instance
            
        Raises:
            InitializationError: If service initialization fails
        """
        try:
            # Create dummy recorder to replace database functionality
            class DummyRecorder:
                def __init__(self):
                    self.field_keys = []
                
                async def save(self, *args, **kwargs):
                    pass
            
            self.DummyRecorder = DummyRecorder
            
            # Initialize components
            self.console = self._imports["ColorfulConsole"]()
            self.settings = self._imports["Settings"](
                self._imports["PROJECT_ROOT"], 
                self.console
            )
            self.cookie_object = self._imports["Cookie"](
                self.settings, 
                self.console
            )
            
            # Get settings data
            settings_data = self.settings.read()
            
            # Update with provided cookie if available
            if self.cookie:
                try:
                    cookie_dict = self.cookie_object.extract(
                        self.cookie, 
                        write=False
                    )
                    settings_data["cookie"] = cookie_dict
                    logger.debug("Updated settings with provided cookie")
                except Exception as e:
                    logger.warning(f"Failed to extract cookie: {str(e)}")
            
            # Override timeout setting
            settings_data["timeout"] = self.timeout
            
            # Initialize parameters
            self.parameters = self._imports["Parameter"](
                self.settings,
                self.cookie_object,
                logger=self._imports["BaseLogger"],
                console=self.console,
                recorder=None,  # No recorder needed
                **settings_data
            )
            
            # Set up headers and cookies
            self.parameters.set_headers_cookie()
            
            logger.info("TikTok service initialized successfully")
            return self
            
        except Exception as e:
            # Restore original directory in case of error
            os.chdir(self._original_dir)
            
            logger.error(f"Service initialization failed: {str(e)}")
            raise InitializationError(f"Failed to initialize TikTok service: {str(e)}")
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Clean up resources when exiting the async context.
        
        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        try:
            # Close HTTP client
            if self.parameters:
                await self.parameters.close_client()
                logger.debug("Closed HTTP client")
            
            # Restore original working directory
            if hasattr(self, '_original_dir'):
                os.chdir(self._original_dir)
                logger.debug(f"Restored working directory to {self._original_dir}")
                
        except Exception as e:
            logger.warning(f"Error during cleanup: {str(e)}")
    
    @gate_keeper()
    @log_service_call(method_type="douyin", tollgate="10-2")
    @cache_result(expire_seconds=600)
    async def get_video_info(
        self, 
        url: str, 
        retries: Optional[int] = None,
        extract_text: bool = False,
        cal_points: bool = True
    ) -> Dict[str, Any]:
        """
        Get detailed information about a TikTok/Douyin video.
        
        Args:
            url: TikTok/Douyin video URL
            retries: Number of retry attempts (defaults to self.max_retries)
            
        Returns:
            Dictionary containing video details
            
        Raises:
            VideoFetchError: If video information cannot be retrieved
        """
        if not self.parameters:
            raise InitializationError(
                "Service not properly initialized. Use 'async with' statement."
            )
        
        # Use class default if retries not specified
        retries = self.max_retries if retries is None else retries
        
        trace_key = request_ctx.get_trace_key()
        logger.info(f"Fetching video info for URL: {url}")
        
        if cal_points:
            total_required = 10  # 基础消耗10分
            
            # 从上下文获取积分信息
            points_info = request_ctx.get_points_info()
            available_points = points_info.get('available_points', 0)
        
            # 验证积分是否足够
            if available_points < total_required:
                error_msg = f"获取基本信息时积分不足: 需要 {total_required} 积分您当前仅有 {available_points} 积分"
                logger.info_to_db(error_msg, extra={"request_id": trace_key})
                raise AudioTranscriptionError(error_msg)
            
            logger.info_to_db(f"获取基本信息时检查通过：所需 {total_required} 积分，可用 {available_points} 积分，需要记录这个消耗", 
                    extra={"request_id": trace_key})

        # Implement retry logic
        for attempt in range(retries + 1):
            try:
                # Extract video ID
                extractor = self._imports["Extractor"](self.parameters)
                video_ids = await extractor.run(url)
                
                if not video_ids:
                    logger.warning(f"Could not extract video ID from URL: {url}")
                    raise VideoFetchError(f"No video ID found in URL: {url}")
                
                video_id = video_ids[0]
                logger.debug(f"Successfully extracted video ID: {video_id}")
                
                # Get video details
                detail = self._imports["Detail"](
                    self.parameters,
                    detail_id=video_id
                )
                
                video_data = await detail.run()
                if not video_data:
                    logger.warning(f"Could not fetch details for video ID: {video_id}")
                    raise VideoFetchError(f"Failed to fetch details for video ID: {video_id}")
                
                # Process the data
                data_extractor = self._imports["DataExtractor"](self.parameters)
                dummy_recorder = self.DummyRecorder()
                
                processed_data = await data_extractor.run(
                    [video_data],
                    dummy_recorder,
                    tiktok=False
                )
                
                if not processed_data:
                    logger.warning(f"Could not process data for video ID: {video_id}")
                    raise VideoFetchError(f"Failed to process data for video ID: {video_id}")
                
                result = processed_data[0]

                if cal_points:
                    # 基础信息获取成功，即使不提取文案，也需要消耗基础积分
                    request_ctx.set_consumed_points(total_required, "基础信息获取成功")
                    logger.info(f"Successfully fetched info for video: {result.get('desc', 'Untitled')}")
                
                # 提取视频文案（如果需要）
                if extract_text and result.get("type") == MediaType.VIDEO and result.get("music_url"):
                    try:
                        video_url = result.get("music_url", "")
                        if not video_url:
                            logger.warning(f"无法获取抖音视频URL，跳过文案提取", extra={"request_id": trace_key})
                            result["transcribed_text"] = "无法获取视频URL"
                        else:
                            logger.info(f"开始提取抖音视频文案: {result.get('note_id', '')}", extra={"request_id": trace_key})
                            
                            # 下载视频
                            try:
                                audio_path = await self._download_douyin_video(video_url, trace_key)                                
                                
                                # 转写音频
                                transcribed_text = await self.script_service.transcribe_audio(audio_path)
                                
                                # 添加到结果中
                                result["transcribed_text"] = transcribed_text
                                logger.info(f"成功提取抖音视频文案", extra={"request_id": trace_key})
                            except AudioDownloadError as e:
                                logger.error(f"下载抖音视频失败: {str(e)}", extra={"request_id": trace_key})
                                result["transcribed_text"] = f"下载视频失败: {str(e)}"
                            except AudioTranscriptionError as e:
                                logger.error(f"转写抖音视频失败: {str(e)}", extra={"request_id": trace_key})
                                result["transcribed_text"] = f"转写视频失败: {str(e)}"
                    except Exception as e:
                        logger.error(f"提取抖音视频文案失败: {str(e)}", exc_info=True, extra={"request_id": trace_key})
                        result["transcribed_text"] = f"提取文案失败: {str(e)}"
                
                logger.info(f"成功获取抖音笔记信息: {result.get('note_id', '')}", extra={"request_id": trace_key})
                return result

                
            except VideoFetchError:
                # Re-raise specific errors without retrying
                raise
                
            except Exception as e:
                if attempt < retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"Attempt {attempt+1}/{retries+1} failed: {str(e)}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {retries+1} attempts failed for URL: {url}")
                    raise VideoFetchError(
                        f"Failed to get video info after {retries+1} attempts: {str(e)}"
                    ) from e
    

    async def _download_douyin_video(self, video_url: str, trace_key: str) -> str:
        logger.info(f"开始下载抖音视频: {video_url}", extra={"request_id": trace_key})
        
        # 创建唯一的临时目录
        download_dir = os.path.join(tempfile.gettempdir(), f"douyin_video_{int(time.time())}")
        os.makedirs(download_dir, exist_ok=True)
        
        try:
            # 根据URL判断是音频还是视频
            is_audio = '.mp3' in video_url or 'music' in video_url
            
            # 生成输出文件路径
            extension = '.mp3' if is_audio else '.mp4'
            output_path = os.path.join(download_dir, f"media_{int(time.time())}{extension}")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": "https://www.douyin.com/",
            }
            
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0) as client:
                async with client.stream('GET', video_url) as response:
                    response.raise_for_status()
                    
                    # 检查响应头中的内容类型
                    content_type = response.headers.get('content-type', '')
                    if not (content_type.startswith('video/') or content_type.startswith('audio/') or 'application/octet-stream' in content_type):
                        raise AudioDownloadError(f"不支持的内容类型: {content_type}")
                    
                    # 以二进制方式写入文件
                    async with aiofiles.open(output_path, 'wb') as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)
            
            # 验证文件是否存在且不为空
            if not os.path.exists(output_path):
                raise AudioDownloadError(f"媒体文件未找到: {output_path}")
                
            if os.path.getsize(output_path) == 0:
                os.remove(output_path)
                raise AudioDownloadError(f"下载的媒体文件为空: {output_path}")
            
            logger.info(f"抖音媒体下载完成: {output_path}", extra={"request_id": trace_key})
            return output_path
            
        except httpx.HTTPError as e:
            error_msg = f"下载媒体时发生HTTP错误: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            raise AudioDownloadError(error_msg) from e
            
        except Exception as e:
            error_msg = f"下载抖音媒体时出现异常: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            
            # 清理临时目录
            try:
                for item in os.listdir(download_dir):
                    os.remove(os.path.join(download_dir, item))
                os.rmdir(download_dir)
            except:
                pass
                
            raise AudioDownloadError(error_msg) from e

    async def get_user_info(
        self, 
        sec_user_id: str, 
        retries: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get detailed information about a TikTok/Douyin user.
        
        Args:
            sec_user_id: TikTok/Douyin user's sec_user_id
            retries: Number of retry attempts (defaults to self.max_retries)
            
        Returns:
            Dictionary containing user details
            
        Raises:
            UserFetchError: If user information cannot be retrieved
        """
        if not self.parameters:
            raise InitializationError(
                "Service not properly initialized. Use 'async with' statement."
            )
        
        # Use class default if retries not specified
        retries = self.max_retries if retries is None else retries
        
        logger.info(f"Fetching user info for sec_user_id: {sec_user_id}")
        
        # Implement retry logic
        for attempt in range(retries + 1):
            try:
                # Get user details
                user = self._imports["User"](
                    self.parameters,
                    sec_user_id=sec_user_id
                )
                
                user_data = await user.run()
                if not user_data:
                    logger.warning(f"Could not fetch details for user: {sec_user_id}")
                    raise UserFetchError(f"Failed to fetch details for user: {sec_user_id}")
                
                # Process the data
                data_extractor = self._imports["DataExtractor"](self.parameters)
                dummy_recorder = self.DummyRecorder()
                
                processed_data = await data_extractor.run(
                    [user_data],
                    dummy_recorder,
                    type_="user"
                )
                
                if not processed_data:
                    logger.warning(f"Could not process data for user: {sec_user_id}")
                    raise UserFetchError(f"Failed to process data for user: {sec_user_id}")
                
                result = processed_data[0]
                logger.info(
                    f"Successfully fetched info for user: {result.get('nickname', 'Unknown')}"
                )
                
                return result
                
            except UserFetchError:
                # Re-raise specific errors without retrying
                raise
                
            except Exception as e:
                if attempt < retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"Attempt {attempt+1}/{retries+1} failed: {str(e)}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {retries+1} attempts failed for user: {sec_user_id}")
                    raise UserFetchError(
                        f"Failed to get user info after {retries+1} attempts: {str(e)}"
                    ) from e
    
    def get_video_info_sync_for_celery(
        url: str, 
        extract_text: bool,
        user_id_for_points: str, 
        trace_id: str,
    ) -> dict:
        logger.info(f"Starting to get video info for url: {url}")
        logger.info(f"Starting to get video info for url: {url}")
        logger.info(f"Starting to get video info for url: {url}")


    @async_cache_result(expire_seconds=600,prefix="tk_service")
    async def get_user_profile_by_url(
        self,
        user_url: str,
        log_extra: Dict[str, Any],
        retries: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        根据 TikTok/抖音用户主页 URL 获取详细的用户信息。

        参数：
            user_url: 用户主页的 URL（可以是分享链接或直接链接）。
            log_extra: 日志附加信息字典。
            retries: 底层操作的重试次数。

        返回：
            包含用户详细信息的字典。

        异常：
            UserFetchError: 如果无法获取用户信息或无法提取 sec_user_id。
            InitializationError: 如果服务未正确初始化。
        """
        if not self.parameters:
            raise InitializationError(
                "服务未正确初始化。请使用 'async with' 语句。"
            )

        _retries = self.max_retries if retries is None else retries
        logger.info(f"开始获取用户主页信息，URL: {user_url}", extra=log_extra)

        try:
            # 步骤 1: 解析 URL 以获取 sec_user_id
            link_extractor = self._imports["Extractor"](self.parameters) # 对应抖音
            extracted_sec_ids = await link_extractor.run(user_url, type_="user")

            if not extracted_sec_ids or not isinstance(extracted_sec_ids, list) or len(extracted_sec_ids) == 0:
                logger.warning(f"无法从 URL 提取 sec_user_id: {user_url}", extra=log_extra)
                raise UserFetchError(f"未能在 URL 中找到 sec_user_id: {user_url}")

            sec_user_id = extracted_sec_ids[0]
            logger.debug(f"成功从 URL 提取 sec_user_id: {sec_user_id}，URL: {user_url}", extra=log_extra)

            # 步骤 2: 使用获取到的 sec_user_id 调用已有的 get_user_info 方法
            user_profile_data = await self.get_user_info(sec_user_id, retries=_retries)
            
            logger.info(f"成功获取用户主页信息，sec_user_id: {sec_user_id}，URL: {user_url}", extra=log_extra)
            return user_profile_data

        except UserFetchError:
            logger.error(f"获取用户主页信息失败，URL: {user_url}（UserFetchError）", exc_info=True, extra=log_extra)
            raise
        except InitializationError:
            logger.error(f"获取用户主页信息时服务未初始化，URL: {user_url}", exc_info=True, extra=log_extra)
            raise
        except Exception as e:
            logger.error(f"获取用户主页信息发生未知错误，URL {user_url}，错误: {str(e)}", exc_info=True, extra=log_extra)
            raise UserFetchError(
                f"获取用户主页信息失败，URL {user_url}，错误: {str(e)}"
            ) from e


    # @gate_keeper() # 根据您的项目需求决定是否保留
    # @log_service_call(method_type="video_comments", tollgate="xx-z") # tollgate 值应根据您的业务逻辑调整
    # @async_cache_result(expire_seconds=600,prefix="tk_service")
    async def get_all_video_comments(
        self,
        video_url: str,
        fetch_replies: bool = False,
        max_comment_pages: Optional[int] = None,
        comments_per_page: int = 20, # 抖音/TikTok 单次请求通常返回的评论数量
        replies_per_comment_page: int = 3, # 如果 fetch_replies 为 True, TikTokDownloader 默认尝试获取的回复数
        platform: Optional[str] = None ,# 可选参数，用于明确指定平台 "douyin" 或 "tiktok"
        log_extra :  Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        获取指定抖音/TikTok视频URL的所有评论。

        参数:
            video_url (str): 视频的URL。
            fetch_replies (bool): 是否获取每条评论的回复。默认为 False。
            max_comment_pages (Optional[int]): 获取评论的最大页数（请求次数）。
                                             如果为 None，则会尝试获取所有可获取的评论页。
                                             注意：子模块内部有其自身的 `max_pages` 默认值。
            comments_per_page (int): 每次请求获取的评论数量。
            replies_per_comment_page (int): 如果 fetch_replies 为 True，每次请求评论的回复时，
                                            尝试获取的回复数量。
            platform (Optional[str]): 明确指定平台 "douyin" 或 "tiktok"。
                                      如果为 None，则尝试从URL推断。

        返回:
            List[Dict[str, Any]]: 评论列表，每个元素是一个包含评论信息的字典。

        可能抛出的异常:
            CommentError: 如果获取评论过程中发生特定于评论的错误。
            VideoFetchError: 如果无法从URL中提取视频ID。
            InitializationError: 如果服务未正确初始化。
            PlatformError: 如果无法确定平台或平台不受支持。
            TikTokError: 其他与TikTok/抖音服务相关的通用错误。
        """
        if not self.parameters:
            raise InitializationError("服务未正确初始化，请确保在 'async with' 语句中使用。")
        logger.info(f"开始为视频URL获取所有评论: {video_url}", extra=log_extra)

        try:
            current_platform = platform
            logger.debug(f"当前操作平台: {current_platform}", extra=log_extra)

            # 根据平台选择正确的链接提取器和评论接口类
            if current_platform == "tiktok":
                link_extractor_cls = self._imports.get("ExtractorTikTok")
                comment_interface_cls = self._imports.get("CommentTikTok")
                if not link_extractor_cls or not comment_interface_cls:
                    raise InitializationError("TikTok 的链接提取器 (ExtractorTikTok) 或评论接口 (CommentTikTok) 未能成功导入。")
            else: # 默认为抖音
                link_extractor_cls = self._imports.get("Extractor")
                comment_interface_cls = self._imports.get("Comment")
                if not link_extractor_cls or not comment_interface_cls:
                    raise InitializationError("抖音的链接提取器 (Extractor) 或评论接口 (Comment) 未能成功导入。")
            
            link_extractor = link_extractor_cls(self.parameters)
            video_ids = await link_extractor.run(video_url, type_="detail")

            if not video_ids or not isinstance(video_ids, list) or not video_ids[0]:
                logger.warning(f"无法从URL中提取视频ID (detail_id): {video_url}", extra=log_extra)
                raise VideoFetchError(f"未能从URL {video_url} 中找到有效的视频ID。")

            detail_id = video_ids[0]
            logger.debug(f"从URL {video_url} 成功提取到视频ID (detail_id): {detail_id}", extra=log_extra)

            # --- 步骤 2: 实例化并运行评论获取器 ---
            # `Comment` 类内部的 `pages` 参数控制总的API请求次数。
            # 如果 `max_comment_pages` 未指定，则使用服务初始化时 `Parameter` 对象中定义的 `max_pages`。
            effective_max_pages = max_comment_pages if max_comment_pages is not None else self.parameters.max_pages
            
            # 根据平台选择使用的 cookie
            current_cookie = None
            if self.cookie: # 如果服务初始化时传入了cookie
                current_cookie = self.cookie
            elif current_platform == "tiktok":
                current_cookie = self.parameters.cookie_str_tiktok or self.parameters.cookie_dict_tiktok
            # else: # douyin
            #     current_cookie = self.parameters.cookie_str or self.parameters.cookie_dict
            
            if isinstance(current_cookie, dict): # Comment 类期望 string 类型的 cookie
                current_cookie_str = self._imports["Cookie"].cookie_dict_to_str_for_header(current_cookie) # 假设有此方法或类似
            else:
                current_cookie_str = current_cookie


            comment_fetcher = comment_interface_cls(
                self.parameters,
                cookie=current_cookie_str, # 传递合适的 cookie 字符串
                item_id=detail_id,
                pages=effective_max_pages,
                count=comments_per_page,
                reply=fetch_replies,
                count_reply=replies_per_comment_page 
            )

            logger.debug(f"开始请求视频ID {detail_id} 的评论数据...", extra=log_extra)
            raw_comments_data = await comment_fetcher.run() # error_text 参数可用于自定义无评论时的日志信息

            if not raw_comments_data: # 可能返回空列表或None
                logger.info(f"视频ID {detail_id} 没有评论，或未能成功获取评论。", extra=log_extra)
                return [] 

            logger.debug(f"成功获取视频ID {detail_id} 的原始评论数据共 {len(raw_comments_data)} 条。", extra=log_extra)

            # --- 步骤 3: 处理和格式化评论数据 ---
            data_extractor = self._imports["DataExtractor"](self.parameters)
            dummy_recorder = self.DummyRecorder() # 使用虚拟记录器，因为我们只提取数据，不保存到子模块的存储

            processed_comments = await data_extractor.run(
                raw_comments_data,
                dummy_recorder,
                type_="comment", # 告知提取器处理的是评论数据
                tiktok=(current_platform == "tiktok") # 传递平台信息给提取器
            )

            logger.info(f"成功获取并处理了 {len(processed_comments)} 条评论 (视频ID: {detail_id}, URL: {video_url})。", extra=log_extra)
            return processed_comments

        except VideoFetchError as vfe:
            logger.error(f"为评论提取视频ID失败 (URL: {video_url}): {str(vfe)}", exc_info=True, extra=log_extra)
            raise # 此类错误通常表示输入URL有问题，直接抛出
        # except PlatformError as pe:
        #     logger.error(f"平台处理错误 (URL: {video_url}): {str(pe)}", exc_info=True, extra=log_extra)
        #     raise
        except InitializationError as ie:
            logger.error(f"服务初始化错误，无法获取评论 (URL: {video_url}): {str(ie)}", exc_info=True, extra=log_extra)
            raise
        # except TikTokError as te: # 捕获子模块或服务定义的其他 TikTokError
        #     logger.error(f"获取评论时发生TikTok/抖音服务相关错误 (URL: {video_url}): {str(te)}", exc_info=True, extra=log_extra)
        #     raise CommentError(f"获取视频评论失败: {str(te)}") from te
        except Exception as e:
            # 对于未知错误，记录详细信息并包装成 CommentError
            logger.error(f"获取视频评论时发生意外错误 (URL: {video_url}): {str(e)}", exc_info=True, extra=log_extra)
            # raise CommentError(f"获取视频 {video_url} 的评论时发生意外错误: {str(e)}") from e
            raise




async def get_video_info(
    url: str, 
    cookie: Optional[str] = None, 
    timeout: int = TikTokService.DEFAULT_TIMEOUT,
    max_retries: int = TikTokService.MAX_RETRIES
) -> Dict[str, Any]:
    """
    Convenience function to get video information without manually managing the service.
    
    Args:
        url: TikTok/Douyin video URL
        cookie: TikTok/Douyin cookie string (optional)
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        
    Returns:
        Dictionary containing video details
        
    Raises:
        VideoFetchError: If video information cannot be retrieved
    """
    async with TikTokService(
        cookie=cookie, 
        timeout=timeout, 
        max_retries=max_retries
    ) as service:
        return await service.get_video_info(url)


async def get_user_info(
    sec_user_id: str, 
    cookie: Optional[str] = None,
    timeout: int = TikTokService.DEFAULT_TIMEOUT,
    max_retries: int = TikTokService.MAX_RETRIES
) -> Dict[str, Any]:
    """
    Convenience function to get user information without manually managing the service.
    
    Args:
        sec_user_id: TikTok/Douyin user's sec_user_id
        cookie: TikTok/Douyin cookie string (optional)
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        
    Returns:
        Dictionary containing user details
        
    Raises:
        UserFetchError: If user information cannot be retrieved
    """
    async with TikTokService(
        cookie=cookie, 
        timeout=timeout, 
        max_retries=max_retries
    ) as service:
        return await service.get_user_info(sec_user_id)


    
