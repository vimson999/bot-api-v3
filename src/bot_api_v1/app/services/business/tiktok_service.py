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

from bot_api_v1.app.core.cache import cache_result
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


# --- Helper function ---
_loop_tiktok = None
try:
    _loop_tiktok = asyncio.get_running_loop()
except RuntimeError:
    _loop_tiktok = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop_tiktok)

def run_async_in_sync_tiktok(coro):
    """专用于 TikTokService 的同步执行异步帮助函数"""
    # ... (实现同 celery_service_logic.py 中的 run_async_in_sync) ...
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            logger.warning("Detected running event loop in run_async_in_sync_tiktok.")
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=300) 
        else:
            return asyncio.run(coro)
    except RuntimeError: 
        return asyncio.run(coro)
    except Exception as e:
        logger.error(f"run_async_in_sync_tiktok failed: {e}", exc_info=True)
        raise


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

        self._imports = {} 
        self._original_dir = os.getcwd()

        class _DummyRecorderInternal: # 使用内部名称避免潜在冲突
            """Placeholder recorder, defined during service init."""
            def __init__(self):
                self.field_keys = []

                # logger.debug("DummyRecorder initialized.")
                pass 
            
            # 同步 save 方法 (如果被同步调用)
            def save(self, *args, **kwargs):
                # logger.debug("DummyRecorder save called (sync).")
                pass
            
        self.DummyRecorder = _DummyRecorderInternal 
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

            # --- 正确的导入语句 (基于子模块根目录在 sys.path 中) ---
            # 现在需要从 src 开始导入
            from src.config import Settings, Parameter
            from src.custom import PROJECT_ROOT # 假设 PROJECT_ROOT 在 src/custom/__init__.py 或 src/custom.py 中
            from src.tools import ColorfulConsole
            from src.module import Cookie
            from src.interface import Detail, User
            from src.link import Extractor
            from src.extract import Extractor as DataExtractor # 别名保持不变
            from src.record import BaseLogger

            # 存储导入的模块/类，供服务实例使用
            self._imports = {
                "Settings": Settings,
                "Parameter": Parameter,
                "PROJECT_ROOT": PROJECT_ROOT,
                "ColorfulConsole": ColorfulConsole,
                "Cookie": Cookie,
                "Detail": Detail,
                "User": User,
                "Extractor": Extractor,
                "DataExtractor": DataExtractor,
                "BaseLogger": BaseLogger
            }
            # --- 导入结束 ---

            logger.debug("Successfully imported TikTok downloader modules using submodule root path strategy")

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
    

# --- 新增的同步上下文管理器方法 ---
    def __enter__(self) -> 'TikTokService':
        """
        [同步] 初始化服务，用于 'with' 语句。
        将 __aenter__ 中的逻辑同步化。
        """
        logger.debug("Entering synchronous context (__enter__)")
        try:
            # !! 在这里执行 __aenter__ 中的初始化逻辑，但要用同步方式 !!
            
            # 1. 创建依赖的对象 (这些通常是同步的)
            self.console = self._imports["ColorfulConsole"]()
            self.settings = self._imports["Settings"](self._imports["PROJECT_ROOT"], self.console)
            self.cookie_object = self._imports["Cookie"](self.settings, self.console)
            
            # 2. 获取设置 (同步)
            settings_data = self.settings.read()
            
            # 3. 处理传入的 Cookie (同步)
            if self.cookie:
                try:
                    cookie_dict = self.cookie_object.extract(self.cookie, write=False)
                    settings_data["cookie"] = cookie_dict
                    logger.debug("[Sync Init] Updated settings with provided cookie")
                except Exception as e:
                    logger.warning(f"[Sync Init] Failed to extract cookie: {str(e)}")
            
            # 4. 设置超时 (同步)
            settings_data["timeout"] = self.timeout
            
            # 5. 初始化 Parameters (这个类的初始化需要是同步的，或者可以同步完成)
            #    假设 Parameter 类的 __init__ 是同步的
            self.parameters = self._imports["Parameter"](
                self.settings, self.cookie_object, logger=self._imports["BaseLogger"],
                console=self.console, recorder=None, **settings_data
            )
            
            # 6. 设置 Headers 和 Cookie (这个方法需要是同步的)
            #    假设 Parameter 类有同步的 set_headers_cookie 方法或在 __init__ 完成
            self.parameters.set_headers_cookie() 
            
            logger.info("Synchronous TikTok service initialized successfully via __enter__")
            return self # !! 必须返回 self !!
            
        except Exception as e:
            logger.error(f"[Sync Init] Service initialization failed via __enter__: {str(e)}", exc_info=True)
            # 清理可能部分初始化的资源？取决于你的具体逻辑
            # 恢复工作目录（如果 _setup_imports 中更改了）
            if hasattr(self, '_original_dir') and os.getcwd() != self._original_dir:
                 try:
                     os.chdir(self._original_dir)
                     logger.debug(f"Restored working directory via __enter__ error path to {self._original_dir}")
                 except Exception as chdir_e:
                     logger.error(f"Failed to restore working directory in __enter__ error path: {chdir_e}")
            raise InitializationError(f"Failed to initialize sync TikTok service: {str(e)}") from e

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        [同步] 清理资源，用于 'with' 语句结束时。
        将 __aexit__ 中的逻辑同步化。
        """
        logger.debug("Exiting synchronous context (__exit__)")
        try:
            # !! 在这里执行 __aexit__ 中的清理逻辑，但要用同步方式 !!
            
            # 1. 关闭 HTTP 客户端
            if self.parameters:
                # !! 关键：需要一种同步关闭客户端的方式 !!
                # 如果 self.parameters.client 是 httpx.Client (同步), 可以直接 close()
                # 如果是 httpx.AsyncClient，则不能直接 close()。
                # 可能需要 self.parameters 提供一个同步关闭方法，或者忽略关闭（不推荐）
                try:
                    # 假设 Parameter 类有一个同步关闭方法或其 client 是同步的
                    if hasattr(self.parameters, 'client') and hasattr(self.parameters.client, 'close') and callable(self.parameters.client.close):
                         self.parameters.client.close() 
                         logger.debug("[Sync Cleanup] Closed synchronous HTTP client via __exit__")
                    elif hasattr(self.parameters, 'close_client_sync') and callable(self.parameters.close_client_sync):
                         self.parameters.close_client_sync()
                         logger.debug("[Sync Cleanup] Called close_client_sync() via __exit__")
                    else:
                         logger.warning("[Sync Cleanup] Cannot determine how to close the HTTP client synchronously in __exit__.")
                except Exception as close_e:
                     logger.error(f"[Sync Cleanup] Error closing HTTP client in __exit__: {close_e}", exc_info=True)

            # 2. 恢复工作目录 (如果更改过)
            if hasattr(self, '_original_dir') and os.getcwd() != self._original_dir:
                os.chdir(self._original_dir)
                logger.debug(f"Restored working directory via __exit__ to {self._original_dir}")
                
        except Exception as e:
            logger.warning(f"Error during synchronous cleanup via __exit__: {str(e)}", exc_info=True)
        # __exit__ 不应重新抛出异常（除非是特意为之），让 with 语句外的代码处理
        return False # 返回 False 表示如果发生异常，异常应该被重新抛出

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
            # class DummyRecorder:
            #     def __init__(self):
            #         self.field_keys = []
                
            #     async def save(self, *args, **kwargs):
            #         pass
            
            # self.DummyRecorder = DummyRecorder
            
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
        extract_text: bool = False
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
                logger.info(f"Successfully fetched info for video: {result.get('desc', 'Untitled')}")

                if total_required > 0:
                    request_ctx.set_consumed_points(total_required, "基础信息获取成功")

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

    # --- 新增的同步方法 (供 Celery 调用) ---
    def get_video_info_sync_for_celery(
        self, 
        url: str, 
        extract_text: bool,
        # --- 替代 request_ctx 的参数 ---
        user_id_for_points: str, 
        trace_id: str 
    ) -> dict:
        """
        [同步执行] 获取抖音视频信息，并可选提取文本。
        为 Celery Task 设计，不依赖 request_ctx，不写数据库。
        """
        log_extra = {"request_id": trace_id, "user_id": user_id_for_points}
        logger.info(f"[Sync TikTok] 开始获取视频信息: {url}, extract_text={extract_text}", extra=log_extra)
        
        points_consumed = 0
        base_cost = 10
        transcription_cost = 0
        media_data = None
        transcribed_text = None
        
        
        # !! 重要：需要同步初始化 !!
        # TikTokService 使用了 __aenter__/__aexit__，这不适用于同步场景。
        # 你需要创建一个同步的初始化方法或在 __init__ 中完成所有设置。
        # 暂时假设可以在 __init__ 后直接使用 self.parameters 等。
        if not self.parameters:
             # 尝试同步初始化 (需要重构 __aenter__ 的逻辑到这里或一个新方法)
             # self._initialize_sync() # 假设有这个方法
             logger.error("[Sync TikTok] 服务未正确同步初始化!", extra=log_extra)
             raise InitializationError("服务未正确同步初始化")

        try:
            # 1. 获取基础视频信息 (包装异步调用)
            async def _fetch_tiktok_video_async():
                # 调用原有的获取 ID 和 Detail 的异步逻辑
                # 但需要确保它们不依赖 request_ctx
                extractor = self._imports["Extractor"](self.parameters)
                video_ids = await extractor.run(url)
                if not video_ids: raise VideoFetchError(f"No video ID found in URL: {url}")
                video_id = video_ids[0]
                
                detail = self._imports["Detail"](self.parameters, detail_id=video_id)
                video_data_raw = await detail.run()
                if not video_data_raw: raise VideoFetchError(f"Failed to fetch details for video ID: {video_id}")
                
                # 处理数据 (这部分通常是同步的)
                data_extractor = self._imports["DataExtractor"](self.parameters)
                dummy_recorder = self.DummyRecorder() # 使用内部的 DummyRecorder
                processed_data = await data_extractor.run([video_data_raw], dummy_recorder, tiktok=False) # 确认这个 run 是 async 还是 sync
                if not processed_data: raise VideoFetchError(f"Failed to process data for video ID: {video_id}")
                
                return processed_data[0]

            try:
                media_data = run_async_in_sync_tiktok(_fetch_tiktok_video_async())
                points_consumed += base_cost
                if not media_data: raise TikTokError("未能获取抖音基础信息")
            except Exception as e:
                raise TikTokError(f"获取抖音基础信息失败: {e}") from e

            # 2. 如果需要提取文本
            if extract_text and media_data.get("type") == MediaType.VIDEO:
                # 获取媒体 URL (可能是 'music_url' 或 'video_url')
                media_url = media_data.get("music_url") or media_data.get("downloads") # 根据你的代码调整
                if media_url:
                    logger.info(f"[Sync TikTok] 开始下载和转写媒体...", extra=log_extra)
                    try:
                        # !! 调用同步下载和转写 !!
                        # audio_path = self._download_douyin_video_sync(media_url, trace_id) # 需要创建同步版本
                        audio_path, _ = self.script_service.download_audio_sync(media_url, trace_id) # 或者调用 ScriptService 的
                        transcribed_text,audio_duration_sec = self.script_service.transcribe_audio_sync(audio_path, trace_id)
                        
                        # 计算积分
                        # audio_duration_sec = 100 # !! 需要获取时长 !!
                        duration_points = ((audio_duration_sec // 60) + (1 if audio_duration_sec % 60 > 0 else 0)) * 10
                        transcription_cost = max(10, duration_points)
                        
                        logger.info(f"[Sync TikTok] 媒体转写成功", extra=log_extra)
                    except (AudioDownloadError, AudioTranscriptionError) as e:
                        logger.error(f"[Sync TikTok] 下载或转写失败: {e}", extra=log_extra)
                        transcribed_text = f"提取文本失败: {str(e)}"
                        transcription_cost = 0
                    except Exception as e:
                         logger.error(f"[Sync TikTok] 提取文本发生意外错误: {e}", exc_info=True, extra=log_extra)
                         transcribed_text = f"提取文本时发生内部错误 ({trace_id})"
                         transcription_cost = 0
                else:
                     transcribed_text = "无法获取媒体URL进行转写"
                     logger.warning("[Sync TikTok] 未找到媒体URL", extra=log_extra)
                
                media_data["transcribed_text"] = transcribed_text # 假设字段名为 transcribed_text
            
            points_consumed = transcription_cost
            
            logger.info(f"[Sync TikTok] 处理成功完成: {url}", extra=log_extra)
            return {"status": "success", "data": media_data, "points_consumed": points_consumed}

        except (TikTokError, InitializationError) as e: # 捕获已知错误
             error_msg = f"处理失败 ({type(e).__name__}): {str(e)}"
             logger.error(f"[Sync TikTok] {error_msg}", extra=log_extra)
             return {"status": "failed", "error": error_msg, "points_consumed": 0}
        except Exception as e: # 捕获其他意外错误
             error_msg = f"发生意外错误: {str(e)}"
             logger.error(f"[Sync TikTok] {error_msg}", exc_info=True, extra=log_extra)
             return {"status": "failed", "error": f"发生内部错误 ({trace_id})", "exception": str(e), "points_consumed": 0}

    


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

