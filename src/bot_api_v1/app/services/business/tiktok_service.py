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
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper


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
        
        # Import required modules only when actually needed
        self._setup_imports()
    
    def _setup_imports(self) -> None:
        """
        Set up the necessary imports from the TikTok downloader library.
        Handles path configuration and imports.
        
        Raises:
            ImportError: If required modules cannot be imported
        """
        try:
            # 使用配置中提供的路径
            tiktok_root = Path(self.tiktok_lib_path)
            
            # Add TikTok downloader path to system path if not already there
            if str(tiktok_root) not in sys.path:
                sys.path.append(str(tiktok_root))
                logger.debug(f"Added {tiktok_root} to Python path")
            
            # Store original directory to restore later
            self._original_dir = os.getcwd()
            
            # Temporarily change working directory for correct module loading
            os.chdir(str(tiktok_root))
            logger.debug(f"Changed working directory to {tiktok_root}")
            
            # Import TikTok downloader modules
            from src.config import Settings, Parameter
            from src.custom import PROJECT_ROOT
            from src.tools import ColorfulConsole
            from src.module import Cookie
            from src.interface import Detail, User
            from src.link import Extractor
            from src.extract import Extractor as DataExtractor
            from src.record import BaseLogger
            
            # Store the imports
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
            
            logger.debug("Successfully imported TikTok downloader modules")
            
        except ImportError as e:
            # Restore directory in case of error
            if hasattr(self, '_original_dir'):
                os.chdir(self._original_dir)
            
            logger.error(f"Failed to import required modules: {str(e)}")
            raise ImportError(f"Could not import TikTok downloader modules: {str(e)}")
    
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
    
    async def get_video_info(
        self, 
        url: str, 
        retries: Optional[int] = None
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
        
        logger.info(f"Fetching video info for URL: {url}")
        
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

