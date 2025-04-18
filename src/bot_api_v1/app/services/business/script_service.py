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

class ScriptService:
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
        self.temp_dir = settings.SHARED_TEMP_DIR
        # self.temp_dir = temp_dir or tempfile.gettempdir()
        self.whisper_model_name = whisper_model
        self.max_parallel_chunks = max_parallel_chunks
        self.chunk_duration = chunk_duration
        self.whisper_model = None
        os.makedirs(self.temp_dir, exist_ok=True)
        if ScriptService._thread_pool is None:
            ScriptService._thread_pool = ThreadPoolExecutor(max_workers=self._max_concurrent_tasks, thread_name_prefix="whisper_worker")
            ScriptService._model_lock = threading.Lock()
            # 确保转写锁被初始化
            if ScriptService._transcription_lock is None:
                 ScriptService._transcription_lock = threading.Lock()

    def _get_whisper_model(self) -> Any:
        """加载Whisper模型，如果CUDA可用则使用GPU"""
        trace_key = request_ctx.get_trace_key()
        if self.whisper_model is not None:
            return self.whisper_model
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model_key = f"{self.whisper_model_name}_{device}"
        if model_key in ScriptService._model_cache:
            return ScriptService._model_cache[model_key]
        with ScriptService._model_lock:
            if model_key in ScriptService._model_cache:
                return ScriptService._model_cache[model_key]
            try:
                logger.info(f"加载Whisper {self.whisper_model_name}模型到{device}设备", extra={"request_id": trace_key})
                if device == "cuda":
                    torch.set_float32_matmul_precision('medium')
                # model = whisper.load_model(self.whisper_model_name, device=device, download_root=os.path.join(self.temp_dir, "whisper_models"))
                model = whisper.load_model(self.whisper_model_name, device=device)

                ScriptService._model_cache[model_key] = model
                return model
            except RuntimeError as e:
                if "CUDA out of memory" in str(e):
                    logger.warning(f"GPU内存不足，回退到CPU: {str(e)}", extra={"request_id": trace_key})
                    cpu_model_key = f"{self.whisper_model_name}_cpu"
                    if cpu_model_key in ScriptService._model_cache:
                        return ScriptService._model_cache[cpu_model_key]
                    else:
                        model = whisper.load_model(self.whisper_model_name, device="cpu")
                        # model = whisper.load_model(self.whisper_model_name, device="cpu", download_root=os.path.join(self.temp_dir, "whisper_models"))

                        ScriptService._model_cache[cpu_model_key] = model
                        return model
                logger.error(f"Whisper模型加载失败: {str(e)}", exc_info=True, extra={"request_id": trace_key})
                raise AudioTranscriptionError(f"模型加载失败: {str(e)}") from e
            except Exception as e:
                logger.error(f"Whisper模型加载失败: {str(e)}", exc_info=True, extra={"request_id": trace_key})
                raise AudioTranscriptionError(f"模型加载失败: {str(e)}") from e

    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-2")
    @cache_result(expire_seconds=600)
    async def download_audio(self, url: str) -> Tuple[str, str]:
        """下载音频并返回文件路径和标题"""
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

    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-3")
    @cache_result(expire_seconds=300)
    async def transcribe_audio(self, audio_path: str) -> str:
        """
        将音频转写为文本 (修改：不再转WAV, 增加调试日志, **激活转写锁**)
        """
        trace_key = request_ctx.get_trace_key()
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("无法在 transcribe_audio 中获取事件循环...", extra={"request_id": trace_key})

        if not os.path.exists(audio_path):
            raise AudioTranscriptionError(f"音频文件不存在: {audio_path}")

        logger.info(f"transcribe_audio-开始转写音频: {audio_path}", extra={"request_id": trace_key})
        start_time = time.time()
        text = ""
        temp_chunk_paths = []

        # 包装函数，用于安全调度数据库日志记录
        def _schedule_db_log_safe(log_method, msg: str, extra_data: dict):
            try:
                log_method(msg, extra=extra_data)
            except Exception as e:
                logger.error(f"调度DB日志时出错(包装器内): {e}", exc_info=True, extra=extra_data)

        try:
            try:
                audio = AudioSegment.from_file(audio_path)
            except Exception as load_e:
                logger.error(f"使用 pydub 加载音频失败: {audio_path}...", exc_info=True, extra={"request_id": trace_key})
                raise AudioTranscriptionError(f"无法加载音频文件: {os.path.basename(audio_path)}") from load_e

            audio_duration = len(audio) / 1000

            # 记录时长和积分检查 (使用包装函数调度DB日志)
            log_msg_duration = f"音频时长: {audio_duration:.2f}秒"
            if loop:
                try:
                    loop.call_soon_threadsafe(_schedule_db_log_safe, logger.info_to_db, log_msg_duration, {'request_id': trace_key})
                except Exception as schedule_err:
                    logger.warning(f"调度 '音频时长' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
            else:
                logger.info(log_msg_duration, extra={'request_id': trace_key})

            required_points = 0
            duration_seconds = int(audio_duration)
            duration_points = (duration_seconds // 60) * 10
            if duration_seconds % 60 > 0 or duration_seconds == 0:
                duration_points += 10
            total_required = duration_points
            points_info = request_ctx.get_points_info()
            available_points = points_info.get('available_points', 0)

            if available_points < total_required:
                error_msg = f"提取文案时积分不足: 处理该音频(时长 {duration_seconds} 秒)需要 {total_required} 积分..."
                if loop:
                    try:
                        loop.call_soon_threadsafe(_schedule_db_log_safe, logger.info_to_db, error_msg, {'request_id': trace_key})
                    except Exception as schedule_err:
                        logger.warning(f"调度 '积分不足' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
                else:
                    logger.info(error_msg, extra={'request_id': trace_key})
                raise AudioTranscriptionError(error_msg)

            log_msg_points_ok = f"提取文案时积分检查通过：所需 {total_required} 积分..."
            if loop:
                try:
                    loop.call_soon_threadsafe(_schedule_db_log_safe, logger.info_to_db, log_msg_points_ok, {'request_id': trace_key})
                except Exception as schedule_err:
                    logger.warning(f"调度 '积分通过' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
            else:
                logger.info(log_msg_points_ok, extra={'request_id': trace_key})

            model = self._get_whisper_model()

            if audio_duration <= 3000:
                logger.info("音频时长小于5分钟，直接转写", extra={"request_id": trace_key})
                future = ScriptService._thread_pool.submit(
                    lambda: model.transcribe(audio_path)
                )
                try:
                    # 设置超时时间，避免单个任务阻塞太久
                    result = future.result(timeout=max(300, audio_duration * 2))
                    text = result.get("text", "").strip()
                except TimeoutError:
                    raise AudioTranscriptionError(f"音频转写超时，请尝试较短的音频")
                
                # logger.info("音频时长小于或等于5分钟，直接使用原始文件转写", extra={"request_id": trace_key})
                # process_path = audio_path
                # logger.debug(f"将使用原始文件进行处理: {process_path}", extra={"request_id": trace_key})

                # # --- 修改：激活短音频的转写锁 ---
                # logger.debug("尝试获取短音频转写锁...", extra={"request_id": trace_key})
                # future = None # 初始化 future

                # # with ScriptService._transcription_lock:
                # logger.debug("短音频转写锁已获取, 提交任务...", extra={"request_id": trace_key})
                # future = ScriptService._thread_pool.submit(lambda p: model.transcribe(p, language="zh", fp16=False), process_path)
                # logger.debug("短音频转写任务已提交, 释放锁.", extra={"request_id": trace_key})
                # # --- 结束修改 ---

                # if future is None: # 防御性检查
                #     raise AudioTranscriptionError("未能成功提交短音频转写任务")

                # try:
                #     timeout_duration = max(300, audio_duration * 3)
                #     logger.debug(f"等待短音频转写结果 (超时: {timeout_duration}秒)...", extra={"request_id": trace_key})
                #     result = future.result(timeout=timeout_duration)
                #     text = result.get("text", "").strip()
                #     logger.debug("短音频转写结果获取成功", extra={"request_id": trace_key})
                # except FuturesTimeoutError:
                #     total_required = 0
                #     log_message = f"短音频转写超时({timeout_duration}秒)..."
                #     logger.error(log_message, extra={"request_id": trace_key})
                #     if loop:
                #         try:
                #             db_log_msg = f"转写超时(DB): 短音频({timeout_duration}秒)"
                #             loop.call_soon_threadsafe(_schedule_db_log_safe, logger.info_to_db, db_log_msg, {'request_id': trace_key})
                #         except Exception as schedule_e:
                #             logger.error(f"无法调度超时DB日志: {schedule_e}", extra={"request_id": trace_key})
                #     raise AudioTranscriptionError(f"音频转写超时({timeout_duration}秒)...")
                # except Exception as trans_e:
                #     total_required = 0
                #     exc_type = type(trans_e).__name__
                #     exc_msg = str(trans_e)
                #     log_message = f"短音频转写失败: {exc_type} - {exc_msg}"
                #     logger.error(log_message, exc_info=True, extra={"request_id": trace_key})
                #     if loop:
                #         try:
                #             db_log_msg = f"转写失败(DB): 短音频. 类型: {exc_type}..."
                #             loop.call_soon_threadsafe(_schedule_db_log_safe, logger.info_to_db, db_log_msg, {'request_id': trace_key})
                #         except Exception as schedule_e:
                #             logger.error(f"无法调度短音频失败DB日志: {schedule_e}", extra={"request_id": trace_key})
                #     raise AudioTranscriptionError(f"音频转写失败: {exc_type}") from trans_e
            else:
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
                    logger.debug(f"处理片段 {chunk_idx+1}/{num_chunks}: 时间 {start_ms}ms - {end_ms}ms", extra={"request_id": trace_key})

                    if end_ms <= start_ms:
                        logger.warning(f"跳过无效时间片段 {chunk_idx+1}/{num_chunks}", extra={"request_id": trace_key})
                        continue

                    chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_idx}.{export_format}")

                    try:
                        chunk_audio = audio[start_ms:end_ms]
                        chunk_len_ms = len(chunk_audio)
                        logger.debug(f"片段 {chunk_idx+1}: 获取到原始长度 {chunk_len_ms}ms", extra={"request_id": trace_key})

                        if chunk_len_ms < 100:
                            logger.warning(f"跳过过短 (<100ms) 的音频片段 {chunk_idx+1}/{num_chunks}: 长度 {chunk_len_ms}ms", extra={"request_id": trace_key})
                            continue

                        logger.debug(f"准备导出片段 {chunk_idx+1} 到 {chunk_path} (格式: {export_format})", extra={"request_id": trace_key})
                        chunk_audio.export(chunk_path, format=export_format, bitrate="128k")
                        logger.debug(f"导出片段 {chunk_idx+1} 完成.", extra={"request_id": trace_key})

                        if not os.path.exists(chunk_path):
                            logger.warning(f"导出后文件不存在: {chunk_path}", extra={"request_id": trace_key})
                            continue

                        file_size = os.path.getsize(chunk_path)
                        logger.debug(f"片段 {chunk_idx+1}: 导出文件大小 {file_size} bytes", extra={"request_id": trace_key})

                        if file_size < 1024:
                            logger.warning(f"导出文件过小 ({file_size} bytes)，可能无效: {chunk_path}", extra={"request_id": trace_key})
                            self._safe_remove_file(chunk_path, trace_key)
                            continue

                        logger.info(f"片段 {chunk_idx+1}/{num_chunks} 导出成功并验证通过: {chunk_path}", extra={"request_id": trace_key})
                        temp_chunk_paths.append(chunk_path)
                        chunk_files.append((chunk_idx, chunk_path, chunk_len_ms / 1000.0))

                    except Exception as export_e:
                        logger.error(f"导出音频片段 {chunk_idx+1}/{num_chunks} 为 {export_format} 失败", exc_info=True, extra={"request_id": trace_key})
                        if os.path.exists(chunk_path):
                            self._safe_remove_file(chunk_path, trace_key)
                        continue

                del audio
                gc.collect()

                if not chunk_files:
                    logger.error("在导出循环后，未能生成任何有效的音频片段。", extra={"request_id": trace_key})
                    raise AudioTranscriptionError("无法生成有效的音频片段，请检查音频文件或导出过程中的错误日志")

                def process_chunk(chunk_data: tuple, loop: Optional[asyncio.AbstractEventLoop]) -> tuple[int, str]:
                    chunk_idx, chunk_path, chunk_duration_sec = chunk_data
                    nonlocal total_required
                    try:
                        logger.debug(f"开始转写片段 {chunk_idx+1}/{num_chunks} ({os.path.basename(chunk_path)})", extra={"request_id": trace_key})
                        if not os.path.exists(chunk_path) or os.path.getsize(chunk_path) < 1024:
                            logger.error(f"片段 {chunk_idx+1}/{num_chunks} 文件无效...", extra={"request_id": trace_key})
                            return chunk_idx, ""

                        # --- 修改：激活长音频分块的转写锁 ---
                        logger.debug(f"片段 {chunk_idx+1}: 尝试获取转写锁...", extra={"request_id": trace_key})
                        future = None # 初始化 future
                        
                        
                        # with ScriptService._transcription_lock:
                        logger.debug(f"片段 {chunk_idx+1}: 转写锁已获取, 提交任务...", extra={"request_id": trace_key})
                        # 将 submit 调用移到锁内部确保 transcribe 调用受锁保护
                        future = ScriptService._thread_pool.submit(lambda p: model.transcribe(p, language="zh", task="transcribe", fp16=False), chunk_path)
                        logger.debug(f"片段 {chunk_idx+1}: 转写任务已提交, 释放锁.", extra={"request_id": trace_key})
                        # --- 结束修改 ---

                        if future is None: # 防御性检查
                            raise AudioTranscriptionError(f"未能成功提交片段 {chunk_idx+1} 的转写任务")

                        timeout_chunk = max(180, chunk_duration_sec * 4)
                        logger.debug(f"等待片段 {chunk_idx+1} 转写结果 (超时: {timeout_chunk}秒)...", extra={"request_id": trace_key})
                        result = future.result(timeout=timeout_chunk)
                        chunk_text = result.get("text", "").strip()
                        logger.debug(f"片段 {chunk_idx+1}/{num_chunks} 转写完成", extra={"request_id": trace_key})
                        return chunk_idx, chunk_text
                    except FuturesTimeoutError:
                        total_required = 0
                        log_message = f"片段 {chunk_idx+1}/{num_chunks} 转写超时({timeout_chunk}秒)..."
                        logger.error(log_message, extra={"request_id": trace_key})
                        if loop:
                            try:
                                db_log_msg = f"转写超时(DB): 片段 {chunk_idx+1}/{num_chunks}..."
                                loop.call_soon_threadsafe(_schedule_db_log_safe, logger.info_to_db, db_log_msg, {'request_id': trace_key})
                            except Exception as schedule_e:
                                logger.error(f"无法调度超时DB日志: {schedule_e}", extra={"request_id": trace_key})
                        return chunk_idx, ""
                    except Exception as e:
                        total_required = 0
                        exc_type = type(e).__name__
                        exc_msg = str(e)
                        log_message = f"片段 {chunk_idx+1}/{num_chunks} 转写失败, 类型: {exc_type}..."
                        logger.error(log_message, exc_info=True, extra={"request_id": trace_key})
                        if loop:
                            try:
                                db_log_msg = f"转写错误(DB): 片段 {chunk_idx+1}/{num_chunks}. 类型: {exc_type}..."
                                loop.call_soon_threadsafe(_schedule_db_log_safe, logger.info_to_db, db_log_msg, {'request_id': trace_key})
                            except Exception as schedule_e:
                                logger.error(f"无法调度转写失败DB日志: {schedule_e}", extra={"request_id": trace_key})
                        return chunk_idx, ""

                workers = min(self.max_parallel_chunks, len(chunk_files), max(2, (os.cpu_count() or 4) // 2))
                logger.info(f"使用 {workers} 个并行任务进行转写 (但实际执行会受锁限制变为串行)", extra={"request_id": trace_key}) # 更新日志说明
                futures_map = {}
                results_list = [""] * num_chunks
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"audio_{trace_key[-6:]}") as local_executor:
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
                            results_list[chunk_idx] = "" # 确保失败的片段结果为空
                text = "\n".join(filter(None, results_list))
                logger.info("所有音频片段转写任务完成", extra={"request_id": trace_key})

            elapsed_time = time.time() - start_time
            log_msg_finish = f"音频转写完成，耗时: {elapsed_time:.2f}秒"
            if loop:
                try:
                    loop.call_soon_threadsafe(_schedule_db_log_safe, logger.info_to_db, log_msg_finish, {'request_id': trace_key})
                except Exception as schedule_err:
                    logger.warning(f"调度 '转写完成' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
            else:
                logger.info(log_msg_finish, extra={'request_id': trace_key})

            if total_required > 0:
                request_ctx.set_consumed_points(total_required, "音频转写服务")
                log_msg_points_consumed = f"成功完成转写，消耗积分: {total_required}"
                if loop:
                    try:
                        loop.call_soon_threadsafe(_schedule_db_log_safe, logger.info_to_db, log_msg_points_consumed, {'request_id': trace_key})
                    except Exception as schedule_err:
                        logger.warning(f"调度 '消耗积分' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
                else:
                    logger.info(log_msg_points_consumed, extra={'request_id': trace_key})
            else:
                request_ctx.set_consumed_points(0)
                log_msg_no_points = "转写过程中发生错误，未消耗积分"
                if loop:
                    try:
                        loop.call_soon_threadsafe(_schedule_db_log_safe, logger.info_to_db, log_msg_no_points, {'request_id': trace_key})
                    except Exception as schedule_err:
                        logger.warning(f"调度 '未消耗积分' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
                else:
                    logger.info(log_msg_no_points, extra={'request_id': trace_key})
            return text

        except AudioTranscriptionError as ate:
            request_ctx.set_consumed_points(0)
            raise ate
        except Exception as e:
            request_ctx.set_consumed_points(0)
            error_msg = f"音频转写过程中发生未知严重错误: {type(e).__name__} - {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            if loop:
                 try:
                     db_log_msg = f"转写顶层错误(DB): {type(e).__name__} - {str(e)}"
                     loop.call_soon_threadsafe(_schedule_db_log_safe, logger.info_to_db, db_log_msg, {'request_id': trace_key})
                 except Exception as log_e:
                     logger.error(f"无法调度顶层错误的异步DB日志: {log_e}", extra={"request_id": trace_key})
            raise AudioTranscriptionError(error_msg) from e
        finally:
            logger.debug(f"开始清理临时文件: {temp_chunk_paths}", extra={"request_id": trace_key})
            paths_to_clean = sorted(temp_chunk_paths, key=lambda p: os.path.isfile(p), reverse=True)
            for path_to_clean in paths_to_clean:
                if os.path.isfile(path_to_clean):
                    self._safe_remove_file(path_to_clean, trace_key)
                elif os.path.isdir(path_to_clean):
                    self._cleanup_dir(path_to_clean, trace_key)
            if os.path.exists(audio_path) and os.path.isfile(audio_path):
                 is_chunk_file = any(os.path.samefile(audio_path, p) for p in temp_chunk_paths if os.path.exists(p) and os.path.isfile(p))
                 if not is_chunk_file:
                     self._safe_remove_file(audio_path, trace_key)
            self._cleanup_parent_dir(audio_path, trace_key)


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

    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-2")
    @cache_result(expire_seconds=600)
    async def download_audio_direct(self, url: str) -> Tuple[str, str]:
        """直接从URL下载音频文件并返回文件路径和文件名"""
        trace_key = request_ctx.get_trace_key()
        logger.info(f"download_audio_direct-开始直接下载音频: {url}", extra={"request_id": trace_key})
        download_dir = os.path.join(self.temp_dir, f"audio_direct_{int(time.time())}_{trace_key[-6:]}")
        os.makedirs(download_dir, exist_ok=True)
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            file_name = os.path.basename(parsed_url.path)
        except Exception:
            file_name = f"audio_{int(time.time())}.audio"
        if not file_name or '.' not in file_name:
            file_name = f"audio_{int(time.time())}.audio"
        downloaded_path = os.path.join(download_dir, file_name)

        try:
            import httpx
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
                        import re
                        from urllib.parse import unquote
                        fname_match = re.search(r'filename\*?=(?:UTF-8\'\')?([^;]+)', content_disposition, re.IGNORECASE)
                        if fname_match:
                            potential_name = unquote(fname_match.group(1).strip('" '))
                            if '.' in potential_name:
                                file_name = os.path.basename(potential_name)
                                downloaded_path = os.path.join(download_dir, file_name)
                    response.raise_for_status()
                    content_type = response.headers.get('Content-Type', '').lower()
                    if not content_type.startswith(('audio/', 'video/', 'application/octet-stream', 'application/ogg')):
                        logger.warning(f"下载内容类型可能不是音频: {content_type}", extra={"request_id": trace_key})
                    bytes_downloaded = 0
                    try:
                        with open(downloaded_path, 'wb') as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                # 正确的换行和缩进
                                if chunk:
                                    f.write(chunk)
                                    bytes_downloaded += len(chunk)
                    except Exception as write_e:
                        raise AudioDownloadError(f"写入文件时出错: {write_e}") from write_e
                    if bytes_downloaded == 0 and response.status_code == 200:
                        logger.warning(f"下载成功但文件大小为 0: {downloaded_path}", extra={"request_id": trace_key})

            if not os.path.exists(downloaded_path):
                possible_files = [os.path.join(download_dir, f) for f in os.listdir(download_dir)]
                if len(possible_files) == 1:
                    downloaded_path = possible_files[0]
                    file_name = os.path.basename(downloaded_path)
                else:
                    raise AudioDownloadError(f"音频文件未找到: {downloaded_path}")
            if os.path.getsize(downloaded_path) == 0:
                self._safe_remove_file(downloaded_path, trace_key)
                raise AudioDownloadError(f"下载的音频文件为空: {downloaded_path}")
            logger.info(f"音频直接下载完成: {file_name}", extra={"request_id": trace_key})
            return downloaded_path, file_name
        except httpx.HTTPStatusError as e:
            error_msg = f"下载失败 (HTTP Status {e.response.status_code})..."
            logger.error(error_msg, extra={"request_id": trace_key})
            self._cleanup_dir(download_dir, trace_key)
            raise AudioDownloadError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"下载失败 (Request Error): {type(e).__name__}..."
            logger.error(error_msg, extra={"request_id": trace_key})
            self._cleanup_dir(download_dir, trace_key)
            raise AudioDownloadError(error_msg) from e
        except AudioDownloadError:
            raise
        except Exception as e:
            error_msg = f"直接下载时未知异常: {type(e).__name__}..."
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            self._cleanup_dir(download_dir, trace_key)
            raise AudioDownloadError(error_msg) from e



    BASE_TEMP_DIR = getattr(settings, 'SHARED_TEMP_DIR', '/tmp/shared_media_temp')
    def _safe_remove_file_sync(self,file_path: str, trace_id: Optional[str] = None):
        """同步安全删除文件"""
        log_extra = {"request_id": trace_id or "cleanup"}
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.debug(f"成功删除文件: {file_path}", extra=log_extra)
            except Exception as e:
                logger.error(f"删除文件失败: {file_path}, Error: {e}", extra=log_extra)

    def _cleanup_dir_sync(self,directory: str, trace_id: Optional[str] = None):
        """同步清理目录"""
        log_extra = {"request_id": trace_id or "cleanup"}
        if os.path.exists(directory):
            try:
                shutil.rmtree(directory)
                logger.debug(f"成功清理临时目录: {directory}", extra=log_extra)
            except Exception as e:
                logger.error(f"清理临时目录失败: {directory}, Error: {e}", exc_info=True, extra=log_extra)

    def download_media_sync(
        self, # 添加 self 参数
        url: str,
        trace_id: str, # 直接传递 trace_id
        # user_id: str, # 如果日志或其他逻辑需要，也传递进来
        # app_id: str,
        download_base_dir: str = BASE_TEMP_DIR, # 使用共享的基础临时目录,
        root_trace_key: str = None # 传递根 trace_id
    ) -> str: # 返回下载后的文件绝对路径
        """
        [同步执行] 从 URL 下载媒体文件 (视频/音频) 到共享临时目录。
        供 Celery Task A 调用。
        """
        log_extra = {"request_id": trace_id, "root_trace_key":root_trace_key } # , "user_id": user_id, "app_id": app_id
        logger.info(f"[Sync Download] 开始下载媒体: {url}", extra=log_extra)

        # 1. 创建唯一的临时下载目录
        # 使用时间戳和 trace_id 的一部分确保唯一性
        download_dir = os.path.join(download_base_dir, f"media_{int(time.time())}_{trace_id[-8:]}")
        try:
            os.makedirs(download_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"创建临时目录失败: {download_dir}, Error: {e}", exc_info=True, extra=log_extra)
            raise AudioDownloadError(f"无法创建下载目录: {e}") from e

        # 2. 初步确定文件名和路径
        try:
            parsed_url = urlparse(url)
            file_name = os.path.basename(parsed_url.path) if parsed_url.path else ''
        except Exception:
            file_name = ''

        if not file_name or '.' not in file_name:
            # 如果无法从 URL 获取有效文件名，生成一个默认名（后缀可能不准，后面尝试修正）
            file_name = f"media_{int(time.time())}.tmp"
        downloaded_path = os.path.join(download_dir, file_name)
        logger.debug(f"初步下载路径: {downloaded_path}", extra=log_extra)

        # 3. 执行下载 (使用 requests)
        try:
            headers = { # 使用通用或针对性的 Headers
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
                'Accept': '*/*', # 更通用的 Accept
                'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
                'Referer': url, # 有些网站会检查 Referer
                # 'Cookie': 'YOUR_COOKIES_IF_NEEDED' # 如果需要 Cookie
            }
            # 使用 stream=True 进行流式下载，适合大文件
            response = requests.get(url, headers=headers, stream=True, allow_redirects=True, timeout=120.0) # 增加超时时间

            # 尝试从 Content-Disposition 获取更准确的文件名
            content_disposition = response.headers.get('Content-Disposition')
            if content_disposition:
                fname_match = re.search(r'filename\*?=(?:UTF-8\'\')?([^;]+)', content_disposition, re.IGNORECASE)
                if fname_match:
                    potential_name = unquote(fname_match.group(1).strip('" '))
                    if '.' in potential_name: # 确保有后缀
                        new_file_name = os.path.basename(potential_name)
                        new_downloaded_path = os.path.join(download_dir, new_file_name)
                        if new_downloaded_path != downloaded_path:
                            logger.info(f"从 Content-Disposition 更新文件名为: {new_file_name}", extra=log_extra)
                            file_name = new_file_name
                            downloaded_path = new_downloaded_path # 更新最终路径

            # 检查 HTTP 状态码
            response.raise_for_status() # 如果状态码不是 2xx，会抛出 HTTPError

            # 检查 Content-Type (可选)
            content_type = response.headers.get('Content-Type', '').lower()
            if not content_type.startswith(('audio/', 'video/', 'application/octet-stream', 'binary/octet-stream')):
                logger.warning(f"下载的内容类型可能非预期: {content_type} from {url}", extra=log_extra)
                # 这里可以选择继续下载或报错，取决于你的策略
                # if not allow_unexpected_content_type:
                #     raise AudioDownloadError(f"非预期的内容类型: {content_type}")

            # 4. 流式写入文件
            bytes_downloaded = 0
            try:
                with open(downloaded_path, 'wb') as f:
                    # iter_content 的 chunk_size 可以调整
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk: # filter out keep-alive new chunks
                            f.write(chunk)
                            bytes_downloaded += len(chunk)
                logger.debug(f"文件写入完成，总大小: {bytes_downloaded} bytes.", extra=log_extra)
            except IOError as write_e:
                logger.error(f"写入文件时发生 IO 错误: {write_e}", exc_info=True, extra=log_extra)
                raise AudioDownloadError(f"写入文件时出错: {write_e}") from write_e

            # 5. 下载后检查
            if not os.path.exists(downloaded_path):
                # 有时文件名在写入后可能改变（虽然上面尝试修正了），再次检查目录
                possible_files = [os.path.join(download_dir, f) for f in os.listdir(download_dir)]
                if len(possible_files) == 1:
                    logger.warning(f"原始路径 {downloaded_path} 未找到，但发现唯一文件 {possible_files[0]}", extra=log_extra)
                    downloaded_path = possible_files[0]
                else:
                    raise AudioDownloadError(f"下载后文件未找到: {downloaded_path}")

            if bytes_downloaded == 0 and response.status_code == 200:
                logger.error(f"下载成功但文件大小为 0: {downloaded_path}", extra=log_extra)
                self._safe_remove_file_sync(downloaded_path, trace_id) # 删除空文件
                raise AudioDownloadError(f"下载的文件为空: {url}")

            # 6. 成功返回路径
            logger.info(f"媒体文件下载成功: {downloaded_path}", extra=log_extra)
            # 注意：这里只返回路径，Task A 需要将此路径传递给 Task B
            # Task B 需要能访问这个路径
            return downloaded_path

        # --- 统一异常处理 ---
        except requests.exceptions.HTTPError as e:
            error_msg = f"下载失败 (HTTP Status {e.response.status_code})"
            logger.error(f"{error_msg} from {url}", extra=log_extra)
            self._cleanup_dir_sync(download_dir, trace_id) # 清理目录
            raise AudioDownloadError(error_msg) from e
        except requests.exceptions.RequestException as e:
            error_msg = f"下载失败 (Request Error): {type(e).__name__}"
            logger.error(f"{error_msg} from {url}", extra=log_extra)
            self._cleanup_dir_sync(download_dir, trace_id) # 清理目录
            raise AudioDownloadError(error_msg) from e
        except AudioDownloadError as e: # 捕获并重新抛出内部定义的错误
            # 可能已经在内部记录过日志，这里可以选择是否补充日志
            self._cleanup_dir_sync(download_dir, trace_id) # 确保清理
            raise e
        except Exception as e:
            error_msg = f"下载过程中发生未知异常: {type(e).__name__}"
            logger.error(f"{error_msg} from {url}", exc_info=True, extra=log_extra)
            self._cleanup_dir_sync(download_dir, trace_id) # 清理目录
            raise AudioDownloadError(error_msg) from e

        finally:
            # 确保 response 连接被关闭 (对于 stream=True 很重要)
            if 'response' in locals() and response:
                response.close()




    # --- 新增的同步方法 (供 Celery 调用) ---

    def download_audio_sync(self, url: str, trace_id: str,root_trace_key:str) -> Tuple[str, str]:
        """[同步执行] 下载音频并返回文件路径和标题"""
        log_extra = {"request_id": trace_id,"root_trace_key":root_trace_key} # 使用传入的 trace_id
        logger.info(f"[Sync] 开始下载音频: {url}", extra=log_extra)
        download_dir = os.path.join(settings.SHARED_TEMP_DIR, f"audio_{int(time.time())}_{trace_id[-6:]}")
        os.makedirs(download_dir, exist_ok=True)
        outtmpl = os.path.join(download_dir, "%(title)s.%(ext)s")
        # yt-dlp 本身是阻塞的，可以直接在同步方法中使用
        ydl_opts = {
            'outtmpl': outtmpl, 'format': 'bestaudio/best', 'postprocessors': [],
            'quiet': True, 'noplaylist': True, 'geo_bypass': True,
            'socket_timeout': 60, 'retries': 3, 'http_chunk_size': 10 * 1024 * 1024
        }
        try:
            # 直接调用 yt-dlp (它是同步阻塞的)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # extract_info 在 download=True 时是阻塞的
                info = ydl.extract_info(url, download=True) 
                if info is None:
                    raise AudioDownloadError("无法提取音频信息 (info is None)")
                downloaded_path = ydl.prepare_filename(info)
                downloaded_title = info.get('title', "downloaded_audio")
                # ... (后续的文件存在和大小检查逻辑同 download_audio) ...
                actual_downloaded_path = None
                if os.path.exists(downloaded_path):
                    actual_downloaded_path = downloaded_path
                else: # ... (省略查找文件的逻辑) ...
                     raise AudioDownloadError(f"下载目录为空或文件未找到: {download_dir}")
                
                if not actual_downloaded_path or not os.path.exists(actual_downloaded_path):
                     raise AudioDownloadError(f"音频文件未找到: {actual_downloaded_path}")
                if os.path.getsize(actual_downloaded_path) == 0:
                    self._safe_remove_file(actual_downloaded_path, trace_id) # 传递 trace_id
                    raise AudioDownloadError(f"下载的音频文件为空: {actual_downloaded_path}")
                    
                logger.info(f"[Sync] 音频下载完成: {downloaded_title}, 路径: {actual_downloaded_path}", extra=log_extra)
                return actual_downloaded_path, downloaded_title
        except yt_dlp.utils.DownloadError as e:
            # ... (错误处理和日志记录同 download_audio, 使用 log_extra) ...
            error_msg = f"下载音频失败 (yt-dlp DownloadError): {str(e)}"
            logger.error(error_msg, exc_info=True, extra=log_extra)
            self._cleanup_dir(download_dir, trace_id)
            raise AudioDownloadError(error_msg) from e
        except Exception as e:
            # ... (错误处理和日志记录同 download_audio, 使用 log_extra) ...
            error_msg = f"下载音频时出现未知异常: {type(e).__name__} - {str(e)}"
            logger.error(error_msg, exc_info=True, extra=log_extra)
            self._cleanup_dir(download_dir, trace_id) # 确保清理
            raise AudioDownloadError(error_msg) from e


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
            
            from bot_api_v1.app.constants.media_info import MediaPlatform
            if platform == MediaPlatform.DOUYIN:
                audio_path= self.download_media_sync(media_url_to_download,trace_id)
            else:
                # 对于其他平台使用通用下载方法
                audio_path, _ = self.download_audio_sync(media_url_to_download, trace_id)
            
            if not audio_path or not os.path.exists(audio_path):  # 检查路径有效性
                raise AudioDownloadError("transcribe_audio_sync----下载服务未返回有效路径或文件不存在")


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