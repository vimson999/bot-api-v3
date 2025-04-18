# bot_api_v1/app/tasks/celery_tiktok_service.py (已修正路径计算)
import logging
import asyncio
import time
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

# 导入所需的原 TikTokService 中的依赖和错误类
try:
    # 尝试从原始路径导入，因为这个新文件在 tasks 下
    from bot_api_v1.app.services.business.tiktok_service import (
        TikTokError, InitializationError, VideoFetchError, UserFetchError, 
        AudioDownloadError, AudioTranscriptionError, MediaType
    )
    from bot_api_v1.app.services.business.script_service import ScriptService
except ImportError:
     # 如果路径或项目结构不同，需要调整
     # 例如: from ..services.business.tiktok_service import ...
     # 例如: from ..services.business.script_service import ScriptService
     logging.error("CeleryTikTokService: 无法导入依赖的服务或错误类，请检查路径！", exc_info=True)
     raise

from bot_api_v1.app.core.logger import logger

# --- 同步执行异步代码的辅助函数 ---
def run_async_in_new_loop(coro):
    try:
        # 尝试获取或设置事件循环 (适用于不同线程环境)
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 检查循环是否正在运行 (通常在新线程/进程中不会)
        if loop.is_running():
             logger.warning("Detected running event loop in run_async_in_new_loop (Celery Task context). Using threadsafe execution.")
             # 在 Celery 环境下，如果检测到正在运行的循环，使用 run_coroutine_threadsafe 可能更安全
             # 但这需要调用者能访问那个循环，比较复杂。
             # 直接运行 asyncio.run 通常在新线程中是安全的。
             # 为了简单，我们先坚持 asyncio.run
             return asyncio.run(coro) # 在新线程中，asyncio.run 会创建新循环
        else:
             return asyncio.run(coro)
             
    except Exception as e:
        logger.error(f"run_async_in_new_loop failed: {e}", exc_info=True)
        raise

class CeleryTikTokService:
    """专门为 Celery Task 设计的、执行 TikTok 相关操作的同步服务类"""
    DEFAULT_TIMEOUT = 30

    # --- 请用这段代码替换你的 __init__ 方法 ---
    def __init__(self, cookie: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT):
        try:
             from bot_api_v1.app.services.business.script_service import ScriptService 
             self.script_service = ScriptService() 
        except ImportError:
             logger.error("CeleryTikTokService: 无法导入 ScriptService!", exc_info=True)
             raise InitializationError("缺少 ScriptService 依赖")
             
        # self._imports = {}
        # self._original_dir = os.getcwd()
        # self.parameters = None
        # self.console = None
        # self.settings_obj = None 
        # self.cookie_object = None
        self.cookie = cookie
        self.timeout = timeout
        
        # 获取项目根目录路径
        current_dir = Path(__file__).resolve().parent
        project_root = current_dir.parents[3]  # bot-api-v1 项目根目录
        self.tiktok_lib_path = project_root / "src" / "bot_api_v1" / "libs" / "tiktok_downloader"
        
        # These will be initialized in __aenter__
        self.console = None
        self.settings = None
        self.cookie_object = None
        self.parameters = None

        self.script_service = ScriptService()

        class DummyRecorder:
            def __init__(self):
                self.field_keys = []
            
            async def save(self, *args, **kwargs):
                pass
            
        self.DummyRecorder = DummyRecorder
        
        # Import required modules only when actually needed
        # self._setup_imports()
        # 执行初始化，包含修正后的路径计算
        try:        
             self._setup_imports() # 这里的执行依赖于上面的路径计算正确
             self._initialize_sync() # 这里的执行依赖于 _setup_imports 成功
             logger.info("CeleryTikTokService 初始化完成。")
             
        except Exception as e:
             # 捕获包括上面提前抛出的 InitializationError 在内的所有初始化错误
             logger.error(f"CeleryTikTokService 初始化失败: {e}", exc_info=True)
             # 统一向上抛出 InitializationError
             raise InitializationError(f"CeleryTikTokService 初始化失败: {e}") from e
    # --- 结束替换区域 ---


    def _setup_imports(self) -> None:
        # --- 复制原 TikTokService 的 _setup_imports 逻辑 ---
        # (你需要确保这里的代码是你TikTokService中实际工作的代码)
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

            # 导入库组件
            from src.config import Settings, Parameter
            from src.custom import PROJECT_ROOT
            from src.tools import ColorfulConsole
            from src.module import Cookie
            from src.interface import Detail, User
            from src.link import Extractor
            from src.extract import Extractor as DataExtractor
            from src.record import BaseLogger
            self._imports = { "Settings": Settings, "Parameter": Parameter, "PROJECT_ROOT": PROJECT_ROOT, "ColorfulConsole": ColorfulConsole, "Cookie": Cookie, "Detail": Detail, "User": User, "Extractor": Extractor, "DataExtractor": DataExtractor, "BaseLogger": BaseLogger }
            logger.debug("CeleryTikTokService: Successfully imported TikTok downloader modules.")

        except Exception as e:
            logger.error(f"CeleryTikTokService: Failed to import TikTok modules: {e}", exc_info=True)
            raise ImportError(f"CeleryTikTokService: Could not import TikTok modules: {e}") from e
        # finally:
        #      # 确保恢复 CWD (如果切换了)
        #      if changed_cwd and os.getcwd() != previous_cwd:
        #          try:
        #              os.chdir(previous_cwd)
        #              logger.debug(f"Restored working directory to {previous_cwd}")
        #          except Exception as chdir_e:
        #              logger.error(f"Failed to restore working directory from _setup_imports: {chdir_e}")


    def _initialize_sync(self) -> None:
        """执行同步初始化，类似原 __enter__"""
        # --- 复制原 __enter__ 的核心逻辑 ---
        # (代码同你上次提供的，看起来没问题)
        try:
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
            logger.debug("CeleryTikTokService: Synchronous initialization complete.")
        except Exception as e:
             logger.error(f"[Celery TikTok Init] Initialization failed: {e}", exc_info=True)
             raise InitializationError(f"Failed sync init: {e}") from e

    def close_sync(self):
        """同步清理资源，类似原 __exit__"""
        # --- 复制原 __exit__ 的核心逻辑 ---
        # (代码同你上次提供的，包含关闭 client 的尝试和 CWD 恢复)
        logger.debug("CeleryTikTokService: Entering synchronous cleanup (close_sync)")
        try:
            if self.parameters:
                try:
                    self.parameters.close_client()
                    logger.debug("Closed HTTP client")
                    
                    if hasattr(self, '_original_dir'):
                        os.chdir(self._original_dir)
                except Exception as close_e:
                     logger.error(f"[Celery TikTok Cleanup] Error closing HTTP client: {close_e}", exc_info=True)
            # CWD 恢复逻辑（如果 _setup_imports 中切换了目录）
            # if os.getcwd() != self._original_dir:
            #     os.chdir(self._original_dir)
            #     logger.debug(f"Restored working directory to {self._original_dir}")
        except Exception as e:
            logger.warning(f"Error during synchronous cleanup: {str(e)}", exc_info=True)


    def get_video_info_sync(
        self,
        url: str,
        extract_text: bool,
        user_id_for_points: str, 
        trace_id: str,
        root_trace_key: str
    ) -> dict:
        """
        [同步执行] 获取抖音视频信息，并可选提取文本。
        这是 CeleryTikTokService 的核心方法。
        """
        # --- 逻辑基本保持不变，依赖于正确的初始化和同步 ScriptService ---
        log_extra = {"request_id": trace_id, "user_id": user_id_for_points,"root_trace_key": root_trace_key}
        logger.info(f"[Celery TikTok Service] 开始获取视频信息: {url}, extract_text={extract_text}", extra=log_extra)

        points_consumed = 0
        base_cost = 10 
        transcription_cost = 0
        media_data = None
        transcribed_text = None

        if not self.parameters:
             logger.error("[Celery TikTok Service] 服务未初始化 (parameters is None)!", extra=log_extra)
             raise InitializationError("服务未初始化")

        try:
            # 1. 获取基础视频信息 (在线程池中运行异步库代码)
            async def _fetch_tiktok_video_async(inner_trace_id: str, inner_url: str):
                log_extra_inner = {"request_id": inner_trace_id}
                logger.debug("[Celery TikTok Service] ---> Entering _fetch_tiktok_video_async (in thread) <---", extra=log_extra_inner)
                # ... (内部调用 extractor, detail, data_extractor 的 await 逻辑) ...
                # ... (包含详细的 DEBUG 日志 和 精确的 TypeError 捕获) ...
                # --- Placeholder Start ---
                logger.debug(f"Self.parameters check: {bool(self.parameters)}")
                extractor = self._imports["Extractor"](self.parameters)
                logger.debug(f"[Async Fetch Inner] Extractor created: {extractor}")
                extractor_run_result = extractor.run(inner_url)
                logger.debug(f"[Async Fetch Inner] extractor.run returned type: {type(extractor_run_result)}")
                if extractor_run_result is None: raise VideoFetchError("Extractor returned None")
                video_ids = await extractor_run_result
                if not video_ids: raise VideoFetchError("No ID")
                video_id = video_ids[0]
                detail = self._imports["Detail"](self.parameters, detail_id=video_id)
                logger.debug(f"[Async Fetch Inner] Detail created: {detail}")
                detail_run_result = detail.run()
                logger.debug(f"[Async Fetch Inner] detail.run returned type: {type(detail_run_result)}")
                if detail_run_result is None: raise VideoFetchError("Detail returned None")
                video_data_raw = await detail_run_result
                if not video_data_raw: raise VideoFetchError("No Detail Data")
                data_extractor = self._imports["DataExtractor"](self.parameters)
                dummy_recorder = self.DummyRecorder()
                logger.debug(f"[Async Fetch Inner] DataExtractor created: {data_extractor}")
                data_extractor_run_result = data_extractor.run([video_data_raw], dummy_recorder, tiktok=False)
                logger.debug(f"[Async Fetch Inner] data_extractor.run returned type: {type(data_extractor_run_result)}")
                processed_data = None
                try: processed_data = await data_extractor_run_result
                except TypeError as te:
                    if "NoneType" in str(te): raise VideoFetchError(f"数据处理失败: {te}") from te
                    else: raise
                except Exception as await_exc: raise VideoFetchError(f"数据处理未知错误: {await_exc}") from await_exc
                if not processed_data: raise VideoFetchError("No Processed Data")
                return processed_data[0]
                # --- Placeholder End ---

            def _run_fetch_in_thread():
                try: return asyncio.run(_fetch_tiktok_video_async(trace_id, url))
                except Exception as thread_e: logger.error(f"[Celery TikTok Service Thread] Error: {thread_e}", exc_info=True, extra=log_extra); raise thread_e

            logger.debug("[Celery TikTok Service] 执行基础信息获取 (ThreadPool)...", extra=log_extra)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_fetch_in_thread)
                try: media_data = future.result(timeout=self.timeout + 10)
                except TimeoutError: raise TikTokError(f"获取基础信息超时 (ThreadPool)")
                except Exception as e: raise TikTokError(f"获取基础信息失败: {e}") from e

            logger.debug("[Celery TikTok Service] 获取到基础信息", extra=log_extra)
            points_consumed = base_cost
            if media_data is None: raise TikTokError("未能获取基础信息")

            # 2. 提取文本
            if extract_text and isinstance(media_data, dict) and media_data.get("type") == MediaType.VIDEO:
                media_url = media_data.get("music_url") or media_data.get("downloads")
                if media_url:
                    logger.info(f"[Celery TikTok Service] 下载和转写...", extra=log_extra)
                    try:
                        audio_path, _ = self.script_service.download_audio_sync(media_url, trace_id)
                        transcribed_text, duration = self.script_service.transcribe_audio_sync(audio_path, trace_id)
                        if duration >= 0: t_cost = max(10, ((int(duration)//60)+(1 if int(duration)%60>0 else 0))*10)
                        else: t_cost = 10
                        transcription_cost = t_cost
                        logger.info(f"[Celery TikTok Service] 转写成功", extra=log_extra)
                    except (AudioDownloadError, AudioTranscriptionError) as e: transcribed_text = f"失败:{e}"; transcription_cost = 0
                    except Exception as e: transcribed_text = f"内部错误({trace_id})"; transcription_cost = 0
                else: transcribed_text = "无URL"; transcription_cost = 0
                if isinstance(media_data, dict): media_data["transcribed_text"] = transcribed_text

            points_consumed += transcription_cost
            logger.info(f"[Celery TikTok Service] 处理成功: {url}", extra=log_extra)
            return {"status": "success", "data": media_data, "points_consumed": points_consumed}

        # 保持错误处理不变
        except (TikTokError, InitializationError, AudioDownloadError, AudioTranscriptionError, VideoFetchError, UserFetchError) as e:
             error_msg = f"处理失败 ({type(e).__name__}): {str(e)}"
             logger.error(f"[Celery TikTok Service] {error_msg}", extra=log_extra, exc_info=False)
             return {"status": "failed", "error": error_msg, "points_consumed": 0}
        except Exception as e:
             error_msg = f"发生意外错误: {str(e)}"
             logger.error(f"[Celery TikTok Service] {error_msg}", exc_info=True, extra=log_extra)
             return {"status": "failed", "error": f"发生内部错误 ({trace_id})", "exception": str(e), "points_consumed": 0}
        finally:
             self.close_sync() # 确保调用清理

    # ... (可能需要的 get_user_info_sync 方法) ...

    def get_basic_video_info_sync_internal(
        self,
        url: str,
        extract_text: bool,
        user_id_for_points: str, 
        trace_id: str
    ) -> dict:
        """
        [同步执行] 获取抖音视频信息，并可选提取文本。
        这是 CeleryTikTokService 的核心方法。
        """
        # --- 逻辑基本保持不变，依赖于正确的初始化和同步 ScriptService ---
        log_extra = {"request_id": trace_id, "user_id": user_id_for_points}
        logger.info(f"[Celery TikTok Service] 开始获取视频信息: {url}, extract_text={extract_text}", extra=log_extra)

        points_consumed = 0
        base_cost = 10 
        transcription_cost = 0
        media_data = None
        transcribed_text = None

        if not self.parameters:
             logger.error("[Celery TikTok Service] 服务未初始化 (parameters is None)!", extra=log_extra)
             raise InitializationError("服务未初始化")

        try:
            # 1. 获取基础视频信息 (在线程池中运行异步库代码)
            async def _fetch_tiktok_video_async(inner_trace_id: str, inner_url: str):
                log_extra_inner = {"request_id": inner_trace_id}
                logger.debug("[Celery TikTok Service] ---> Entering _fetch_tiktok_video_async (in thread) <---", extra=log_extra_inner)
                # ... (内部调用 extractor, detail, data_extractor 的 await 逻辑) ...
                # ... (包含详细的 DEBUG 日志 和 精确的 TypeError 捕获) ...
                # --- Placeholder Start ---
                logger.debug(f"Self.parameters check: {bool(self.parameters)}")
                extractor = self._imports["Extractor"](self.parameters)
                logger.debug(f"[Async Fetch Inner] Extractor created: {extractor}")
                extractor_run_result = extractor.run(inner_url)
                logger.debug(f"[Async Fetch Inner] extractor.run returned type: {type(extractor_run_result)}")
                if extractor_run_result is None: raise VideoFetchError("Extractor returned None")
                video_ids = await extractor_run_result
                if not video_ids: raise VideoFetchError("No ID")
                video_id = video_ids[0]
                detail = self._imports["Detail"](self.parameters, detail_id=video_id)
                logger.debug(f"[Async Fetch Inner] Detail created: {detail}")
                detail_run_result = detail.run()
                logger.debug(f"[Async Fetch Inner] detail.run returned type: {type(detail_run_result)}")
                if detail_run_result is None: raise VideoFetchError("Detail returned None")
                video_data_raw = await detail_run_result
                if not video_data_raw: raise VideoFetchError("No Detail Data")
                data_extractor = self._imports["DataExtractor"](self.parameters)
                dummy_recorder = self.DummyRecorder()
                logger.debug(f"[Async Fetch Inner] DataExtractor created: {data_extractor}")
                data_extractor_run_result = data_extractor.run([video_data_raw], dummy_recorder, tiktok=False)
                logger.debug(f"[Async Fetch Inner] data_extractor.run returned type: {type(data_extractor_run_result)}")
                processed_data = None
                try: processed_data = await data_extractor_run_result
                except TypeError as te:
                    if "NoneType" in str(te): raise VideoFetchError(f"数据处理失败: {te}") from te
                    else: raise
                except Exception as await_exc: raise VideoFetchError(f"数据处理未知错误: {await_exc}") from await_exc
                if not processed_data: raise VideoFetchError("No Processed Data")
                return processed_data[0]
                # --- Placeholder End ---

            def _run_fetch_in_thread():
                try: return asyncio.run(_fetch_tiktok_video_async(trace_id, url))
                except Exception as thread_e: logger.error(f"[Celery TikTok Service Thread] Error: {thread_e}", exc_info=True, extra=log_extra); raise thread_e

            logger.debug("[Celery TikTok Service] 执行基础信息获取 (ThreadPool)...", extra=log_extra)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_fetch_in_thread)
                try: media_data = future.result(timeout=self.timeout + 10)
                except TimeoutError: raise TikTokError(f"获取基础信息超时 (ThreadPool)")
                except Exception as e: raise TikTokError(f"获取基础信息失败: {e}") from e

            logger.debug("[Celery TikTok Service] 获取到基础信息", extra=log_extra)
            points_consumed = base_cost
            if media_data is None: raise TikTokError("未能获取基础信息")


            logger.info(f"[Celery TikTok Service] 处理成功: {url},media_data is{media_data}", extra=log_extra)
            return {"status": "success", "data": media_data, "points_consumed": points_consumed}

        # 保持错误处理不变
        except (TikTokError, InitializationError, AudioDownloadError, AudioTranscriptionError, VideoFetchError, UserFetchError) as e:
             error_msg = f"处理失败 ({type(e).__name__}): {str(e)}"
             logger.error(f"[Celery TikTok Service] {error_msg}", extra=log_extra, exc_info=False)
             return {"status": "failed", "error": error_msg, "points_consumed": 0}
        except Exception as e:
             error_msg = f"发生意外错误: {str(e)}"
             logger.error(f"[Celery TikTok Service] {error_msg}", exc_info=True, extra=log_extra)
             return {"status": "failed", "error": f"发生内部错误 ({trace_id})", "exception": str(e), "points_consumed": 0}
        finally:
             self.close_sync() # 确保调用清理