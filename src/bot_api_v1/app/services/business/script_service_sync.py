# -*- coding: utf-8 -*-
"""
音频转写脚本服务模块 (已修改：不再转WAV, 增加调试日志, **激活转写锁用于测试**)

提供音频下载、转写和处理相关功能。
"""
import os
import time
import tempfile
from typing import Tuple, Optional, Dict, Any
from pathlib import Path
import asyncio
import threading # 确保导入 threading
import gc # 导入 gc

import requests # 使用同步库 requests
import shutil # 用于清理目录
import re

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import torch
import whisper
import yt_dlp
from pydub import AudioSegment
from bot_api_v1.app.core.config import settings # 假设你有配置文件

# 假设这些导入路径是正确的
from bot_api_v1.app.core.cache import cache_result,cache_result_sync
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper

class AudioDownloadError(Exception):
    """音频下载过程中出现的错误"""
    pass

class AudioTranscriptionError(Exception):
    """音频转写过程中出现的错误"""
    pass

class ScriptService_Sync:
    """脚本服务类，提供音频下载与转写功能"""
    _model_cache = {}
    _thread_pool = None
    _max_concurrent_tasks = 20
    _model_lock = None
    _transcription_lock = None # 用于并发测试的锁

    def __init__(self,
                 temp_dir: Optional[str] = None,
                 whisper_model: str = settings.WHISPER_MODEL,
                 max_parallel_chunks: int = 4,
                 chunk_duration: int = 60):
        self.temp_dir = settings.SHARED_MNT_DIR
        # self.temp_dir = temp_dir or tempfile.gettempdir()
        self.whisper_model_name = whisper_model
        self.max_parallel_chunks = max_parallel_chunks
        self.chunk_duration = chunk_duration
        self.whisper_model = None

        # os.makedirs(self.temp_dir, exist_ok=True)

        if ScriptService_Sync._thread_pool is None:
            ScriptService_Sync._thread_pool = ThreadPoolExecutor(max_workers=self._max_concurrent_tasks, thread_name_prefix="whisper_worker")
            ScriptService_Sync._model_lock = threading.Lock()
            # 确保转写锁被初始化
            if ScriptService_Sync._transcription_lock is None:
                 ScriptService_Sync._transcription_lock = threading.Lock()


    def _get_whisper_model(self) -> Any:
        """加载Whisper模型，如果CUDA可用则使用GPU"""
        trace_key = request_ctx.get_trace_key()
        if self.whisper_model is not None:
            return self.whisper_model
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model_key = f"{self.whisper_model_name}_{device}"
        if model_key in ScriptService_Sync._model_cache:
            return ScriptService_Sync._model_cache[model_key]
        with ScriptService_Sync._model_lock:
            if model_key in ScriptService_Sync._model_cache:
                return ScriptService_Sync._model_cache[model_key]
            try:
                logger.info(f"加载Whisper {self.whisper_model_name}模型到{device}设备", extra={"request_id": trace_key})
                if device == "cuda":
                    torch.set_float32_matmul_precision('medium')
                # model = whisper.load_model(self.whisper_model_name, device=device, download_root=os.path.join(self.temp_dir, "whisper_models"))
                model = whisper.load_model(self.whisper_model_name, device=device)

                ScriptService_Sync._model_cache[model_key] = model
                return model
            except RuntimeError as e:
                if "CUDA out of memory" in str(e):
                    logger.warning(f"GPU内存不足，回退到CPU: {str(e)}", extra={"request_id": trace_key})
                    cpu_model_key = f"{self.whisper_model_name}_cpu"
                    if cpu_model_key in ScriptService_Sync._model_cache:
                        return ScriptService_Sync._model_cache[cpu_model_key]
                    else:
                        model = whisper.load_model(self.whisper_model_name, device="cpu")
                        # model = whisper.load_model(self.whisper_model_name, device="cpu", download_root=os.path.join(self.temp_dir, "whisper_models"))

                        ScriptService_Sync._model_cache[cpu_model_key] = model
                        return model
                logger.error(f"Whisper模型加载失败: {str(e)}", exc_info=True, extra={"request_id": trace_key})
                raise AudioTranscriptionError(f"模型加载失败: {str(e)}") from e
            except Exception as e:
                logger.error(f"Whisper模型加载失败: {str(e)}", exc_info=True, extra={"request_id": trace_key})
                raise AudioTranscriptionError(f"模型加载失败: {str(e)}") from e

    def _safe_remove_file(self, file_path: str, trace_key: str) -> None:
        """安全删除文件，忽略错误"""
        try:
            if os.path.exists(file_path) and os.path.isfile(file_path):
                os.remove(file_path)
                logger.debug(f"已删除文件: {file_path}", extra={"request_id": trace_key})
        except Exception as e:
            logger.warning(f"删除文件失败 {file_path}: {type(e).__name__} - {str(e)}", extra={"request_id": trace_key})

    def _cleanup_dir(self, dir_path: str, trace_key: str) -> None:
        """清理目录及其内容（仅限文件）(增加 item_path 初始化)"""
        item_path = None # 防御性初始化
        try:
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                logger.debug(f"开始清理目录: {dir_path}", extra={"request_id": trace_key})
                items = os.listdir(dir_path)
                logger.debug(f"目录中的项目: {items}", extra={"request_id": trace_key})
                for item in items:
                    item_path = os.path.join(dir_path, item)
                    if os.path.isfile(item_path):
                        self._safe_remove_file(item_path, trace_key)
                try:
                     os.rmdir(dir_path)
                     logger.debug(f"已删除空目录: {dir_path}", extra={"request_id": trace_key})
                except OSError as e:
                     logger.warning(f"删除目录失败（可能非空） {dir_path}: {e}", extra={"request_id": trace_key})
        except Exception as e:
            logger.warning(f"清理目录时发生错误 {dir_path}: {type(e).__name__} - {str(e)}", exc_info=True, extra={"request_id": trace_key})

    def _cleanup_parent_dir(self, file_path: str, trace_key: str) -> None:
        """尝试清理文件所在的父目录(如果为空)"""
        try:
            parent_dir = os.path.dirname(file_path)
            if parent_dir and os.path.exists(parent_dir) and parent_dir != self.temp_dir and parent_dir != os.path.abspath(os.sep):
            # if parent_dir and os.path.exists(parent_dir) and parent_dir != settings.SHARED_TEMP_DIR and parent_dir != os.path.abspath(os.sep):
                # 检查目录是否为空
                if not os.listdir(parent_dir):
                    self._cleanup_dir(parent_dir, trace_key)
        except Exception as e:
            logger.debug(f"尝试清理父目录失败: {parent_dir}, Error: {str(e)}", extra={"request_id": trace_key})

    @cache_result_sync(
        expire_seconds = 1800,
        prefix="transcribe_audio_sync_",
        key_args=['original_url'] # 缓存不应依赖这些请求上下文变量
    )
    def transcribe_audio_sync(self, media_url_to_download:str, platform:str ,original_url: str,audio_path: str, trace_id: str) -> str:
        """[同步执行] 将音频转写为文本"""
        log_extra = {"request_id": trace_id}

        if not os.path.exists(audio_path):
            logger.info(f"[Transcribe Audio {trace_id=}] 音频文件不存在: {audio_path}", extra=log_extra)
            if not media_url_to_download:
                raise AudioTranscriptionError(f"音频文件不存在: {audio_path} 并且 media_url_to_download 为空")


        logger.info(f"[Sync] 开始转写音频: {audio_path},original_url is {original_url}", extra=log_extra)
        start_time = time.time()
        text = ""
        temp_chunk_paths = [] # 用于分块清理

        try:
            # 加载音频和计算时长 (这部分是同步阻塞的)
            try:
                audio = AudioSegment.from_file(audio_path)
                audio_duration = len(audio) / 1000
            except Exception as load_e:
                raise AudioTranscriptionError(f"无法加载音频文件: {os.path.basename(audio_path)}") from load_e

            logger.info(f"[Sync] 音频时长: {audio_duration:.2f}秒", extra=log_extra)            
            model = self._get_whisper_model() # 获取模型 (内部有锁)

            # 临时设置50分钟
            if audio_duration <= 3000: 
                logger.info("[Sync] 音频时长小于50分钟，直接转写", extra=log_extra)
                
                result = model.transcribe(audio_path, language="zh", task="transcribe", fp16=False)
                text = result.get("text", "").strip()
                logger.info("[Sync] 转写完成.", extra=log_extra)
            else:
                 # !! 需要在这里实现长音频的分块、并行处理（如果需要）和合并逻辑 !!
                 # 这会比较复杂，需要将 transcribe_audio 中的分块和线程池逻辑
                 # 移植到这里，并确保它们是同步阻塞完成的。
                 # 简单起见，暂时返回错误或提示不支持长音频
                 logger.warning(f"[Sync] 长音频 (>5分钟) 的同步分块转写逻辑未在此示例中实现！", extra=log_extra)
                 # raise AudioTranscriptionError("同步接口暂不支持超过5分钟的音频")
                 text = "[同步接口暂不支持长音频处理]" # 或者返回提示信息

            elapsed_time = time.time() - start_time
            logger.info(f"[Sync] 音频转写完成，耗时: {elapsed_time:.2f}秒", extra=log_extra)
            
            return {"status": "success", "text": text, "audio_duration": audio_duration}
        except AudioTranscriptionError as ate:
            raise ate # 直接抛出已知错误
        except Exception as e:
            error_msg = f"[Sync] 音频转写过程中发生未知严重错误: {type(e).__name__} - {str(e)}"
            logger.error(error_msg, exc_info=True, extra=log_extra)
            raise AudioTranscriptionError(error_msg) from e
        finally:
            # 清理逻辑保持不变，使用 self._safe_remove_file / _cleanup_dir
            logger.debug(f"开始清理临时文件和目录: {temp_chunk_paths}", extra={"request_id": trace_id})
            paths_to_clean = sorted(temp_chunk_paths, key=lambda p: os.path.isfile(p), reverse=True)
            for path_to_clean in paths_to_clean:
                if os.path.isfile(path_to_clean):
                    self._safe_remove_file(path_to_clean, trace_id)
                elif os.path.isdir(path_to_clean):
                    self._cleanup_dir(path_to_clean, trace_id)

            if os.path.exists(audio_path) and os.path.isfile(audio_path):
                 is_temp_chunk = False
                 for temp_dir in filter(os.path.isdir, temp_chunk_paths):
                     try:
                        # Use os.path.commonpath on normalized paths for robust check
                        norm_audio_path = os.path.normpath(audio_path)
                        norm_temp_dir = os.path.normpath(temp_dir)
                        if os.path.commonpath([norm_audio_path, norm_temp_dir]) == norm_temp_dir:
                             is_temp_chunk = True
                             break
                     except ValueError: # Paths might be on different drives etc.
                         pass
                 if not is_temp_chunk:
                     self._safe_remove_file(audio_path, trace_id)
                 else:
                     logger.debug(f"跳过删除原始文件，因为它是一个临时分块: {audio_path}", extra={"request_id": trace_id})

            self._cleanup_parent_dir(audio_path, trace_id)
            if torch.cuda.is_available():
                 try:
                     torch.cuda.empty_cache()
                     logger.debug("已调用 torch.cuda.empty_cache()", extra={"request_id": trace_id})
                 except Exception as cuda_e:
                     logger.warning(f"调用 torch.cuda.empty_cache() 时出错: {cuda_e}", extra={"request_id": trace_id})
            gc.collect()