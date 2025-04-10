# -*- coding: utf-8 -*-
"""
音频转写脚本服务模块 (已修改：使用 faster-whisper, 支持并行转写, 修复日志调度, 增加 OMP 错误说明)

提供音频下载、转写和处理相关功能。
"""
import os
import time
import tempfile
from typing import Tuple, Optional, Dict, Any
from pathlib import Path
import asyncio
import threading
import gc
import functools # Import functools for partial

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import torch
from faster_whisper import WhisperModel # 使用 faster-whisper
import yt_dlp
from pydub import AudioSegment

# 假设这些导入路径是正确的
from bot_api_v1.app.core.cache import cache_result
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper

# OMP: Error #15 / OpenMP Runtime Conflict Information:
# If you encounter errors like "OMP: Error #15: Initializing libiomp5.dylib..."
# it indicates multiple OpenMP libraries are loaded (e.g., from NumPy/MKL, PyTorch, CTranslate2).
# This can cause performance issues or incorrect results.
# Recommended Mitigation (Run *before* starting the Python app):
# 1. Limit threads via environment variables (try low values first, e.g., 1 or 2):
#    export OMP_NUM_THREADS=1
#    export MKL_NUM_THREADS=1
#    export CT2_NUM_THREADS=1 (or CT2_INTER_THREADS/CT2_INTRA_THREADS)
# 2. (Use with extreme caution, potential for crashes/errors)
#    export KMP_DUPLICATE_LIB_OK=TRUE
# 3. Ensure consistent library installation sources (e.g., all conda-forge or specific pip wheels).

class AudioDownloadError(Exception):
    """音频下载过程中出现的错误"""
    pass

class AudioTranscriptionError(Exception):
    """音频转写过程中出现的错误"""
    pass

class ScriptService:
    """脚本服务类，提供音频下载与转写功能 (使用 faster-whisper, 支持并行)"""
    _model_cache = {}
    _thread_pool = None
    _max_concurrent_tasks = int(os.environ.get("WHISPER_GLOBAL_MAX_TASKS", 20)) # 全局池大小可配置
    _model_lock = None

    def __init__(self,
                 temp_dir: Optional[str] = None,
                 whisper_model: Optional[str] = None, # 改为 Optional，优先环境变量
                 max_parallel_chunks: Optional[int] = None, # 改为 Optional
                 chunk_duration: int = 60,
                 # 新增：允许外部传入配置覆盖
                 cpu_compute_type_override: Optional[str] = None,
                 gpu_compute_type_override: Optional[str] = None,
                 intra_threads_override: Optional[int] = None):

        self.temp_dir = temp_dir or tempfile.gettempdir()
        os.makedirs(self.temp_dir, exist_ok=True)

        # --- 配置优先级：传入参数 > 环境变量 > 默认值 ---
        self.whisper_model_name = whisper_model or os.environ.get("WHISPER_MODEL", "base") # 默认 base
        self.max_parallel_chunks = max_parallel_chunks if max_parallel_chunks is not None else int(os.environ.get("WHISPER_MAX_PARALLEL_CHUNKS", 4)) # 默认 4
        self.chunk_duration = chunk_duration # 这个通常不需要频繁改

        # 配置覆盖
        self._cpu_compute_type_override = cpu_compute_type_override or os.environ.get("WHISPER_CPU_COMPUTE_TYPE")
        self._gpu_compute_type_override = gpu_compute_type_override or os.environ.get("WHISPER_GPU_COMPUTE_TYPE")
        self._intra_threads_override = intra_threads_override if intra_threads_override is not None else os.environ.get("WHISPER_INTRA_THREADS")

        # 内部线程数计算（给个默认逻辑，但允许覆盖）
        self._default_intra_threads = 1 # 默认保守为 1 (避免OMP冲突)
        try:
            cpu_cores = os.cpu_count()
            if cpu_cores and cpu_cores > 1:
                 # 可以尝试更激进的默认值，例如核心数的一半，但需谨慎 OMP 冲突
                 # self._default_intra_threads = max(1, cpu_cores // 2)
                 pass # 保持默认 1 似乎更安全
        except NotImplementedError:
            pass
        # 应用覆盖值（如果提供了）
        self.intra_threads = int(self._intra_threads_override) if self._intra_threads_override else self._default_intra_threads
        logger.info(f"ScriptService initialized: model={self.whisper_model_name}, max_chunks={self.max_parallel_chunks}, intra_threads={self.intra_threads}")


        # 初始化共享资源
        if ScriptService._thread_pool is None:
            ScriptService._thread_pool = ThreadPoolExecutor(max_workers=self._max_concurrent_tasks, thread_name_prefix="whisper_worker")
            ScriptService._model_lock = threading.Lock()

    def _determine_compute_type(self, device: str) -> str:
        """根据设备和配置确定 compute_type"""
        if device == "cuda":
            # 优先使用覆盖值，其次默认 float16
            return self._gpu_compute_type_override or "float16"
        else: # CPU
            # 优先使用覆盖值，其次默认 float32 (基于测试的稳定选择)
            return self._cpu_compute_type_override or "float32"

    def _get_whisper_model(self) -> WhisperModel:
        trace_key = request_ctx.get_trace_key()
        forced_device = os.environ.get("WHISPER_DEVICE")
        if forced_device and forced_device in ["cpu", "cuda"]:
             device = forced_device
             logger.info(f"使用环境变量强制指定设备: {device}", extra={"request_id": trace_key})
        else:
             device = "cuda" if torch.cuda.is_available() else "cpu"

        compute_type = self._determine_compute_type(device)

        # --- 修改：确定 cpu_threads 的值 ---
        # 从 __init__ 中获取配置的线程数 (原 self.intra_threads)
        configured_threads = self.intra_threads
        # 仅当在 CPU 上运行时，才将此值用于 cpu_threads 参数
        cpu_threads_to_pass = configured_threads if device == "cpu" else 0 # 0 或 None 可能表示让库自动决定，或者不传此参数
                                                                           # faster-whisper 文档中 cpu_threads=0 表示使用默认计算
                                                                           # 我们之前配置的 self.intra_threads=1 是明确的，所以这里用它
        # 更新缓存键以反映使用的是 cpu_threads (仅当 device=cpu 时相关)
        thread_key_part = f"cpu_th{cpu_threads_to_pass}" if device == "cpu" else "gpu_th_auto" # 或者不包含 GPU 线程信息
        model_key = f"{self.whisper_model_name}_{device}_{compute_type}_{thread_key_part}"

        if model_key in ScriptService._model_cache:
            logger.debug(f"从缓存获取 faster-whisper 模型: {model_key}", extra={"request_id": trace_key})
            return ScriptService._model_cache[model_key]

        with ScriptService._model_lock:
            if model_key in ScriptService._model_cache:
                logger.debug(f"从缓存获取 faster-whisper 模型 (在锁内检查): {model_key}", extra={"request_id": trace_key})
                return ScriptService._model_cache[model_key]

            try:
                # --- 修改：移除 intra_threads, 添加 cpu_threads ---
                log_msg = f"加载 faster-whisper '{self.whisper_model_name}' 模型到 {device} (compute: {compute_type}"
                if device == "cpu":
                    log_msg += f", cpu_threads: {cpu_threads_to_pass}"
                log_msg += ")"
                logger.info(log_msg, extra={"request_id": trace_key})

                model_kwargs = {
                    "device": device,
                    "compute_type": compute_type,
                }
                if device == "cpu":
                    # 只有在 CPU 上才传递 cpu_threads 参数
                    model_kwargs["cpu_threads"] = cpu_threads_to_pass

                # 使用解包传递参数
                model = WhisperModel(self.whisper_model_name, **model_kwargs)

                ScriptService._model_cache[model_key] = model
                logger.info(f"模型 {model_key} 加载成功并缓存", extra={"request_id": trace_key})
                return model
            # ... OOM 和其他异常处理逻辑保持不变 ...
            except RuntimeError as e:
                 if "CUDA" in str(e).upper() and "memory" in str(e).lower():
                     # ... (OOM 处理逻辑，记得也要用 cpu_threads) ...
                     logger.warning(f"GPU 内存不足 ({device}, {compute_type})，尝试回退到 CPU: {str(e)}", extra={"request_id": trace_key})
                     device = "cpu"
                     compute_type = self._determine_compute_type(device)
                     # CPU 回退时也使用配置的线程数
                     cpu_threads_fallback = self.intra_threads # 使用 __init__ 中计算的值
                     cpu_model_key_part = f"cpu_th{cpu_threads_fallback}"
                     cpu_model_key = f"{self.whisper_model_name}_{device}_{compute_type}_{cpu_model_key_part}"
                     if cpu_model_key in ScriptService._model_cache:
                         return ScriptService._model_cache[cpu_model_key]
                     else:
                         logger.info(f"回退加载 CPU 模型: {cpu_model_key}", extra={"request_id": trace_key})
                         model = WhisperModel(
                             self.whisper_model_name,
                             device=device,
                             compute_type=compute_type,
                             cpu_threads=cpu_threads_fallback # 使用 cpu_threads
                         )
                         ScriptService._model_cache[cpu_model_key] = model
                         logger.info(f"CPU 模型 {cpu_model_key} 加载成功并缓存", extra={"request_id": trace_key})
                         return model
                 else:
                     logger.error(f"加载 faster-whisper 模型时发生运行时错误: {str(e)}", exc_info=True, extra={"request_id": trace_key})
                     raise AudioTranscriptionError(f"模型加载失败 (RuntimeError): {str(e)}") from e
            except Exception as e:
                 logger.error(f"加载 faster-whisper 模型失败: {str(e)}", exc_info=True, extra={"request_id": trace_key})
                 raise AudioTranscriptionError(f"模型加载失败: {str(e)}") from e

    # --- 音频下载方法保持不变 ---
    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-2")
    @cache_result(expire_seconds=600)
    async def download_audio(self, url: str) -> Tuple[str, str]:
        # ... (download_audio implementation remains the same as previous correct version) ...
        trace_key = request_ctx.get_trace_key()
        logger.info(f"download_audio-开始下载音频: {url}", extra={"request_id": trace_key})
        download_dir = os.path.join(self.temp_dir, f"audio_{int(time.time())}_{trace_key[-6:]}")
        os.makedirs(download_dir, exist_ok=True)
        outtmpl = os.path.join(download_dir, "%(title)s.%(ext)s")
        ydl_opts = {
            'outtmpl': outtmpl, 'format': 'bestaudio/best', 'postprocessors': [],
            'quiet': True, 'noplaylist': True, 'geo_bypass': True,
            'socket_timeout': 60, 'retries': 3, 'http_chunk_size': 10 * 1024 * 1024
        }
        try:
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
                logger.info(f"音频下载完成: {downloaded_title}, 路径: {actual_downloaded_path}", extra={"request_id": trace_key})
                if not actual_downloaded_path or not os.path.exists(actual_downloaded_path):
                    possible_files = [os.path.join(download_dir, f) for f in os.listdir(download_dir)]
                    if not possible_files:
                        raise AudioDownloadError(f"下载目录为空，无法找到音频文件: {download_dir}")
                    actual_downloaded_path = max(possible_files, key=os.path.getctime)
                    if not os.path.exists(actual_downloaded_path):
                         raise AudioDownloadError(f"音频文件未找到: {actual_downloaded_path}")

                if os.path.getsize(actual_downloaded_path) == 0:
                    self._safe_remove_file(actual_downloaded_path, trace_key)
                    raise AudioDownloadError(f"下载的音频文件为空: {actual_downloaded_path}")
                return actual_downloaded_path, downloaded_title
        except yt_dlp.utils.DownloadError as e:
            error_msg = f"下载音频失败 (yt-dlp DownloadError): {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            self._cleanup_dir(download_dir, trace_key)
            raise AudioDownloadError(error_msg) from e
        except Exception as e:
            error_msg = f"下载音频时出现未知异常: {type(e).__name__} - {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            try:
                self._cleanup_dir(download_dir, trace_key)
            except Exception as cleanup_e:
                logger.error(f"下载异常后清理目录失败: {cleanup_e}", extra={"request_id": trace_key})
            raise AudioDownloadError(error_msg) from e

    # --- 转写方法，使用 faster-whisper 并行处理 ---
    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-3")
    @cache_result(expire_seconds=300)
    async def transcribe_audio(self, audio_path: str) -> str:
        trace_key = request_ctx.get_trace_key()
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("无法在 transcribe_audio 中获取事件循环...", extra={"request_id": trace_key})

        if not os.path.exists(audio_path):
            raise AudioTranscriptionError(f"音频文件不存在: {audio_path}")

        logger.info(f"transcribe_audio (faster-whisper)-开始转写音频: {audio_path}", extra={"request_id": trace_key})
        start_time = time.time()
        text = ""
        temp_chunk_paths = []
        total_required = 0

        # --- 修复: 使用 functools.partial 包装日志调用 ---
        def _schedule_db_log_safe(log_method, msg: str, extra_data: dict):
            # 使用 functools.partial 创建一个无参数的可调用对象，
            # 它在被调用时会执行 log_method(msg, extra=extra_data)
            wrapped_log_call = functools.partial(log_method, msg, extra=extra_data)
            if loop:
                try:
                    # 传递包装后的调用给 call_soon_threadsafe
                    loop.call_soon_threadsafe(wrapped_log_call)
                except Exception as e:
                    logger.error(f"调度DB日志时出错(包装器内): {e}", exc_info=True, extra=extra_data)
            else:
                try:
                    # 如果没有事件循环，直接在当前线程执行包装后的调用
                    wrapped_log_call()
                except Exception as e:
                    logger.error(f"直接记录DB日志时出错(无事件循环): {e}", exc_info=True, extra=extra_data)

        try:
            # --- 加载音频和积分检查逻辑 ---
            try:
                audio = AudioSegment.from_file(audio_path)
            except Exception as load_e:
                logger.error(f"使用 pydub 加载音频失败: {audio_path}...", exc_info=True, extra={"request_id": trace_key})
                raise AudioTranscriptionError(f"无法加载音频文件: {os.path.basename(audio_path)}") from load_e

            audio_duration = len(audio) / 1000
            log_msg_duration = f"音频时长: {audio_duration:.2f}秒"
            _schedule_db_log_safe(logger.info_to_db, log_msg_duration, {'request_id': trace_key}) # 使用修复后的调度器

            duration_seconds = int(audio_duration)
            duration_points = (duration_seconds // 60) * 10
            if duration_seconds % 60 > 0 or duration_seconds == 0:
                duration_points += 10
            total_required = duration_points
            points_info = request_ctx.get_points_info()
            available_points = points_info.get('available_points', 0)

            if available_points < total_required:
                error_msg = f"提取文案时积分不足: 处理该音频(时长 {duration_seconds} 秒)需要 {total_required} 积分..."
                _schedule_db_log_safe(logger.info_to_db, error_msg, {'request_id': trace_key}) # 使用修复后的调度器
                total_required = 0
                raise AudioTranscriptionError(error_msg)

            log_msg_points_ok = f"提取文案时积分检查通过：所需 {total_required} 积分..."
            _schedule_db_log_safe(logger.info_to_db, log_msg_points_ok, {'request_id': trace_key}) # 使用修复后的调度器

            model = self._get_whisper_model()

            # --- 短音频处理路径 ---
            if audio_duration <= 300:
                logger.info("音频时长小于或等于5分钟，直接转写", extra={"request_id": trace_key})
                process_path = audio_path
                logger.debug(f"将使用原始文件进行处理: {process_path}", extra={"request_id": trace_key})
                future = None
                segments_iterable = None
                info = None
                try:
                    future = ScriptService._thread_pool.submit(
                        model.transcribe, process_path, language="zh", task="transcribe"
                    )
                    logger.debug("短音频转写任务已提交.", extra={"request_id": trace_key})
                    timeout_duration = max(300, audio_duration * 4)
                    logger.debug(f"等待短音频转写结果 (超时: {timeout_duration}秒)...", extra={"request_id": trace_key})
                    segments_iterable, info = future.result(timeout=timeout_duration)
                    text = " ".join([seg.text.strip() for seg in segments_iterable])
                    logger.debug(f"短音频转写结果获取成功. 语言: {info.language}", extra={"request_id": trace_key})
                except FuturesTimeoutError:
                    total_required = 0
                    log_message = f"短音频转写超时({timeout_duration}秒)..."
                    logger.error(log_message, extra={"request_id": trace_key})
                    db_log_msg = f"转写超时(DB): 短音频({timeout_duration}秒)"
                    _schedule_db_log_safe(logger.info_to_db, db_log_msg, {'request_id': trace_key}) # 使用修复后的调度器
                    raise AudioTranscriptionError(f"音频转写超时({timeout_duration}秒)...")
                except Exception as trans_e:
                    total_required = 0
                    exc_type = type(trans_e).__name__
                    exc_msg = str(trans_e)
                    log_message = f"短音频转写失败: {exc_type} - {exc_msg}"
                    logger.error(log_message, exc_info=True, extra={"request_id": trace_key})
                    db_log_msg = f"转写失败(DB): 短音频. 类型: {exc_type}..."
                    _schedule_db_log_safe(logger.info_to_db, db_log_msg, {'request_id': trace_key}) # 使用修复后的调度器
                    raise AudioTranscriptionError(f"音频转写失败: {exc_type}") from trans_e

            # --- 长音频处理路径 ---
            else:
                # 分块导出逻辑... (与上版相同)
                optimal_chunk_duration = min(max(100, int(audio_duration / 40)), 180)
                chunk_duration = optimal_chunk_duration if optimal_chunk_duration != self.chunk_duration else self.chunk_duration
                num_chunks = int(audio_duration // chunk_duration) + (1 if audio_duration % chunk_duration != 0 else 0)
                export_format = "mp3"
                logger.info(f"音频将被分割为 {num_chunks} 个片段 (每段约 {chunk_duration} 秒，格式：{export_format}) 进行并行处理", extra={"request_id": trace_key})
                chunk_dir = os.path.join(self.temp_dir, f"chunks_{int(time.time())}_{trace_key[-6:]}")
                os.makedirs(chunk_dir, exist_ok=True)
                temp_chunk_paths.append(chunk_dir)
                chunk_files = []
                logger.info(f"开始导出 {num_chunks} 个音频片段...", extra={"request_id": trace_key})
                for chunk_idx in range(num_chunks):
                    start_ms = chunk_idx * chunk_duration * 1000
                    end_ms = min((chunk_idx + 1) * chunk_duration * 1000, len(audio))
                    if end_ms <= start_ms: continue
                    chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_idx}.{export_format}")
                    try:
                        chunk_audio = audio[start_ms:end_ms]
                        chunk_len_ms = len(chunk_audio)
                        if chunk_len_ms < 100: continue
                        chunk_audio.export(chunk_path, format=export_format, bitrate="128k")
                        if not os.path.exists(chunk_path) or os.path.getsize(chunk_path) < 1024:
                             logger.warning(f"导出片段 {chunk_idx+1} 无效或过小，跳过.", extra={"request_id": trace_key})
                             self._safe_remove_file(chunk_path, trace_key)
                             continue
                        temp_chunk_paths.append(chunk_path)
                        chunk_files.append((chunk_idx, chunk_path, chunk_len_ms / 1000.0))
                    except Exception as export_e:
                        logger.error(f"导出音频片段 {chunk_idx+1} 失败", exc_info=True, extra={"request_id": trace_key})
                        self._safe_remove_file(chunk_path, trace_key)

                del audio
                gc.collect()

                if not chunk_files:
                    logger.error("未能生成任何有效的音频片段。", extra={"request_id": trace_key})
                    raise AudioTranscriptionError("无法生成有效的音频片段")

                # --- 并行处理分块 (无锁) ---
                def process_chunk(chunk_data: tuple, loop: Optional[asyncio.AbstractEventLoop]) -> tuple[int, str]:
                    chunk_idx, chunk_path, chunk_duration_sec = chunk_data
                    nonlocal total_required
                    segments_iterable = None
                    info = None
                    try:
                        logger.debug(f"开始转写片段 {chunk_idx+1}/{num_chunks} ({os.path.basename(chunk_path)})", extra={"request_id": trace_key})
                        if not os.path.exists(chunk_path) or os.path.getsize(chunk_path) < 1024:
                            logger.error(f"片段 {chunk_idx+1}/{num_chunks} 文件无效...", extra={"request_id": trace_key})
                            return chunk_idx, ""
                        logger.debug(f"直接调用转写片段 {chunk_idx+1}...", extra={"request_id": trace_key})
                        segments_iterable, info = model.transcribe(
                            chunk_path, language="zh", task="transcribe", beam_size=5, word_timestamps=False
                        )
                        chunk_text = " ".join([seg.text.strip() for seg in segments_iterable])
                        logger.debug(f"片段 {chunk_idx+1}/{num_chunks} 转写完成. 语言: {info.language}", extra={"request_id": trace_key})
                        return chunk_idx, chunk_text
                    except TimeoutError: # 基本不会被同步调用触发
                         total_required = 0
                         log_message = f"片段 {chunk_idx+1}/{num_chunks} 转写意外超时..."
                         logger.error(log_message, extra={"request_id": trace_key})
                         db_log_msg = f"转写意外超时(DB): 片段 {chunk_idx+1}/{num_chunks}..."
                         _schedule_db_log_safe(logger.info_to_db, db_log_msg, {'request_id': trace_key}) # 使用修复后的调度器
                         return chunk_idx, ""
                    except Exception as e:
                        total_required = 0
                        exc_type = type(e).__name__
                        exc_msg = str(e)
                        log_message = f"片段 {chunk_idx+1}/{num_chunks} 转写失败, 类型: {exc_type}..."
                        logger.error(log_message, exc_info=True, extra={"request_id": trace_key})
                        db_log_msg = f"转写错误(DB): 片段 {chunk_idx+1}/{num_chunks}. 类型: {exc_type}..."
                        _schedule_db_log_safe(logger.info_to_db, db_log_msg, {'request_id': trace_key}) # 使用修复后的调度器
                        return chunk_idx, ""

                workers = min(self.max_parallel_chunks, len(chunk_files), max(1, (os.cpu_count() or 4)))
                logger.info(f"使用 {workers} 个并行工作线程进行转写", extra={"request_id": trace_key})
                futures_map = {}
                results_list = [""] * num_chunks
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"audio_proc_{trace_key[-6:]}") as local_executor:
                    for chunk_data in chunk_files:
                        chunk_idx = chunk_data[0]
                        future = local_executor.submit(process_chunk, chunk_data, loop)
                        futures_map[future] = chunk_idx
                    for future in as_completed(futures_map):
                        chunk_idx = futures_map[future]
                        try:
                            original_index, result_text = future.result()
                            results_list[original_index] = result_text
                        except Exception as future_e:
                            logger.error(f"处理 future 结果时发生意外错误 (片段索引 {chunk_idx}): {future_e}", exc_info=True, extra={"request_id": trace_key})
                            results_list[chunk_idx] = ""

                text = "\n".join(filter(None, results_list))
                logger.info("所有音频片段并行转写任务完成", extra={"request_id": trace_key})

            # --- 转写完成后的处理逻辑 ---
            elapsed_time = time.time() - start_time
            log_msg_finish = f"音频转写完成，耗时: {elapsed_time:.2f}秒"
            _schedule_db_log_safe(logger.info_to_db, log_msg_finish, {'request_id': trace_key}) # 使用修复后的调度器

            if total_required > 0:
                request_ctx.set_consumed_points(total_required, "音频转写服务 (faster-whisper, 并行)")
                log_msg_points_consumed = f"成功完成转写，消耗积分: {total_required}"
                _schedule_db_log_safe(logger.info_to_db, log_msg_points_consumed, {'request_id': trace_key}) # 使用修复后的调度器
            else:
                request_ctx.set_consumed_points(0)
                log_msg_no_points = "转写过程中发生错误或超时，未消耗积分"
                _schedule_db_log_safe(logger.info_to_db, log_msg_no_points, {'request_id': trace_key}) # 使用修复后的调度器

            return text

        except AudioTranscriptionError as ate:
            request_ctx.set_consumed_points(0)
            raise ate
        except Exception as e:
            request_ctx.set_consumed_points(0)
            error_msg = f"音频转写过程中发生未知严重错误: {type(e).__name__} - {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            db_log_msg = f"转写顶层错误(DB): {type(e).__name__} - {str(e)}"
            _schedule_db_log_safe(logger.info_to_db, db_log_msg, {'request_id': trace_key}) # 使用修复后的调度器
            raise AudioTranscriptionError(error_msg) from e
        finally:
            # --- 清理逻辑 ---
            logger.debug(f"开始清理临时文件和目录: {temp_chunk_paths}", extra={"request_id": trace_key})
            paths_to_clean = sorted(temp_chunk_paths, key=lambda p: os.path.isfile(p), reverse=True)
            for path_to_clean in paths_to_clean:
                if os.path.isfile(path_to_clean):
                    self._safe_remove_file(path_to_clean, trace_key)
                elif os.path.isdir(path_to_clean):
                    self._cleanup_dir(path_to_clean, trace_key)

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
                     self._safe_remove_file(audio_path, trace_key)
                 else:
                     logger.debug(f"跳过删除原始文件，因为它是一个临时分块: {audio_path}", extra={"request_id": trace_key})

            self._cleanup_parent_dir(audio_path, trace_key)
            if torch.cuda.is_available():
                 try:
                     torch.cuda.empty_cache()
                     logger.debug("已调用 torch.cuda.empty_cache()", extra={"request_id": trace_key})
                 except Exception as cuda_e:
                     logger.warning(f"调用 torch.cuda.empty_cache() 时出错: {cuda_e}", extra={"request_id": trace_key})
            gc.collect()

    # --- 清理方法保持不变 ---
    def _safe_remove_file(self, file_path: str, trace_key: str) -> None:
        # ... (implementation remains the same) ...
        try:
            if os.path.exists(file_path) and os.path.isfile(file_path):
                os.remove(file_path)
                logger.debug(f"已删除文件: {file_path}", extra={"request_id": trace_key})
        except Exception as e:
            logger.warning(f"删除文件失败 {file_path}: {type(e).__name__} - {str(e)}", extra={"request_id": trace_key})


    def _cleanup_dir(self, dir_path: str, trace_key: str) -> None:
        # ... (implementation remains the same) ...
        item_path = None
        try:
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                logger.debug(f"开始清理目录内容: {dir_path}", extra={"request_id": trace_key})
                for item in os.listdir(dir_path):
                    item_path = os.path.join(dir_path, item)
                    if os.path.isfile(item_path):
                        self._safe_remove_file(item_path, trace_key)
                try:
                    os.rmdir(dir_path)
                    logger.debug(f"已删除空目录: {dir_path}", extra={"request_id": trace_key})
                except OSError as e:
                    logger.warning(f"删除目录失败（可能非空或权限问题） {dir_path}: {e}", extra={"request_id": trace_key})
        except Exception as e:
            logger.warning(f"清理目录时发生错误 {dir_path}: {type(e).__name__} - {str(e)}", exc_info=True, extra={"request_id": trace_key})


    def _cleanup_parent_dir(self, file_path: str, trace_key: str) -> None:
        # ... (implementation remains the same) ...
        try:
            parent_dir = os.path.dirname(file_path)
            is_temp_parent = parent_dir and parent_dir.startswith(self.temp_dir) and parent_dir != self.temp_dir and os.path.abspath(parent_dir) != os.path.abspath(self.temp_dir)
            if is_temp_parent and os.path.exists(parent_dir):
                if not os.listdir(parent_dir):
                    self._cleanup_dir(parent_dir, trace_key)
                else:
                    logger.debug(f"父目录非空，不删除: {parent_dir}", extra={"request_id": trace_key})
        except Exception as e:
            logger.info(f"尝试清理父目录时出错: {parent_dir}, Error: {str(e)}", extra={"request_id": trace_key})

    # --- Direct Download 方法保持不变 ---
    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-2")
    @cache_result(expire_seconds=600)
    async def download_audio_direct(self, url: str) -> Tuple[str, str]:
        # ... (download_audio_direct implementation remains the same as previous correct version) ...
        trace_key = request_ctx.get_trace_key()
        logger.info(f"download_audio_direct-开始直接下载音频: {url}", extra={"request_id": trace_key})
        download_dir = os.path.join(self.temp_dir, f"audio_direct_{int(time.time())}_{trace_key[-6:]}")
        os.makedirs(download_dir, exist_ok=True)
        file_name = f"audio_{int(time.time())}.audio"

        try:
            from urllib.parse import urlparse, unquote
            import re
            import httpx

            parsed_url = urlparse(url)
            path_basename = os.path.basename(unquote(parsed_url.path))
            if path_basename and '.' in path_basename:
                file_name = path_basename
            downloaded_path = os.path.join(download_dir, file_name)

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
                'Accept': 'audio/webm,audio/ogg,audio/wav,audio/*;q=0.9,application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': url,
            }

            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=60.0) as client:
                async with client.stream("GET", url) as response:
                    content_disposition = response.headers.get('Content-Disposition')
                    if content_disposition:
                        fname_match = re.search(r'filename\*?=(?:UTF-8\'\')?([^;]+)', content_disposition, re.IGNORECASE)
                        if fname_match:
                            potential_name = unquote(fname_match.group(1).strip('"\' '))
                            if potential_name and '.' in potential_name:
                                file_name = os.path.basename(potential_name)
                                downloaded_path = os.path.join(download_dir, file_name)

                    response.raise_for_status()
                    content_type = response.headers.get('Content-Type', '').lower()
                    if not content_type.startswith(('audio/', 'video/', 'application/octet-stream', 'application/ogg', 'binary/octet-stream')):
                        logger.warning(f"下载内容类型可能不是音频: {content_type}", extra={"request_id": trace_key})

                    bytes_downloaded = 0
                    try:
                        with open(downloaded_path, 'wb') as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    bytes_downloaded += len(chunk)
                    except Exception as write_e:
                        raise AudioDownloadError(f"写入文件时出错: {write_e}") from write_e

                    if bytes_downloaded == 0 and response.status_code == 200:
                         content_length = response.headers.get('Content-Length')
                         if content_length is not None and int(content_length) > 0:
                              logger.error(f"下载成功但文件大小为 0，与 Content-Length 不符: {downloaded_path}", extra={"request_id": trace_key})
                              raise AudioDownloadError(f"下载的音频文件为空，但服务器指示非空: {downloaded_path}")
                         else:
                              logger.warning(f"下载成功但文件大小为 0 (可能服务器文件为空): {downloaded_path}", extra={"request_id": trace_key})


            if not os.path.exists(downloaded_path):
                 possible_files = [f for f in os.listdir(download_dir) if os.path.isfile(os.path.join(download_dir, f))]
                 if len(possible_files) == 1:
                     actual_filename = possible_files[0]
                     actual_downloaded_path = os.path.join(download_dir, actual_filename)
                     logger.info(f"实际下载文件路径为: {actual_downloaded_path}", extra={"request_id": trace_key})
                     downloaded_path = actual_downloaded_path
                     file_name = actual_filename
                 else:
                      logger.error(f"下载后在目录 {download_dir} 中未找到预期的或唯一的文件。", extra={"request_id": trace_key})
                      raise AudioDownloadError(f"音频文件下载后未找到")

            final_size = os.path.getsize(downloaded_path)
            if final_size == 0:
                 logger.warning(f"最终确认下载的文件大小为 0: {downloaded_path}", extra={"request_id": trace_key})

            logger.info(f"音频直接下载完成: {file_name}, 大小: {final_size} bytes", extra={"request_id": trace_key})
            return downloaded_path, file_name
        except httpx.HTTPStatusError as e:
            error_msg = f"下载失败 (HTTP Status {e.response.status_code} for url: {e.request.url})..."
            logger.error(error_msg, extra={"request_id": trace_key})
            self._cleanup_dir(download_dir, trace_key)
            raise AudioDownloadError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"下载失败 (Request Error): {type(e).__name__} for url: {e.request.url if e.request else 'N/A'}..."
            logger.error(error_msg, extra={"request_id": trace_key})
            self._cleanup_dir(download_dir, trace_key)
            raise AudioDownloadError(error_msg) from e
        except AudioDownloadError:
            self._cleanup_dir(download_dir, trace_key)
            raise
        except Exception as e:
            error_msg = f"直接下载时未知异常: {type(e).__name__}..."
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            self._cleanup_dir(download_dir, trace_key)
            raise AudioDownloadError(error_msg) from e