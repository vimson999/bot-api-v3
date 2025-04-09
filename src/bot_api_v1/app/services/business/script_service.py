# -*- coding: utf-8 -*-
"""
音频转写脚本服务模块 (已修改以支持从工作线程安全调用异步DB日志)

提供音频下载、转写和处理相关功能。
"""
import os
import time
import tempfile
from typing import Tuple, Optional, Dict, Any
from pathlib import Path
import asyncio # 导入 asyncio
# import traceback # 如果 exc_info=True 不能满足需求，则可能需要导入 traceback

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import torch
import whisper
import yt_dlp
from pydub import AudioSegment

# 假设这些导入路径是正确的
from bot_api_v1.app.core.cache import cache_result
from bot_api_v1.app.core.logger import logger # 使用修改后的 logger 接口
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
# log_service 和 tasks.base 的导入保留在 logger.py 内部使用，这里不需要

class AudioDownloadError(Exception):
    """音频下载过程中出现的错误"""
    pass


class AudioTranscriptionError(Exception):
    """音频转写过程中出现的错误"""
    pass


class ScriptService:
    """脚本服务类，提供音频下载与转写功能"""
    # 添加类级别的模型缓存和线程池
    _model_cache = {}  # 类变量，用于缓存不同设备上的不同模型
    _thread_pool = None  # 类变量，共享线程池
    _max_concurrent_tasks = 20  # 最大并发任务数
    _model_lock = None  # 模型加载锁
    # >>> 新增：类级别的转写锁，用于调试并发问题 <<<
    _transcription_lock = None


    def __init__(self,
                 temp_dir: Optional[str] = None,
                 whisper_model: str = "small",
                 max_parallel_chunks: int = 4,
                 chunk_duration: int = 60):
        """
        初始化脚本服务

        Args:
            temp_dir: 临时文件存储目录，默认使用系统临时目录
            whisper_model: Whisper模型名称, 默认为"small"
            max_parallel_chunks: 并行处理的最大音频片段数
            chunk_duration: 音频分割的片段时长(秒)
        """
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.whisper_model_name = whisper_model
        self.max_parallel_chunks = max_parallel_chunks
        self.chunk_duration = chunk_duration
        self.whisper_model = None

        # 确保临时目录存在
        os.makedirs(self.temp_dir, exist_ok=True)

        # 初始化类变量（仅首次）
        if ScriptService._thread_pool is None:
            import threading
            ScriptService._thread_pool = ThreadPoolExecutor(
                max_workers=self._max_concurrent_tasks,
                thread_name_prefix="whisper_worker"
            )
            ScriptService._model_lock = threading.Lock()
            # >>> 初始化转写锁 <<<
            ScriptService._transcription_lock = threading.Lock()

    def _get_whisper_model(self) -> Any:
        """
        加载Whisper模型，如果CUDA可用则使用GPU (代码同前)
        """
        # (此部分代码与之前版本相同，为了简洁省略，假设没有改动)
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()

        if self.whisper_model is not None:
            return self.whisper_model

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model_key = f"{self.whisper_model_name}_{device}"

        # 检查缓存中是否已有模型
        if model_key in ScriptService._model_cache:
            return ScriptService._model_cache[model_key]

        # 使用锁确保模型只被加载一次
        with ScriptService._model_lock:
            # 双重检查，防止在等待锁期间其他线程已加载模型
            if model_key in ScriptService._model_cache:
                return ScriptService._model_cache[model_key]

            try:
                logger.info(f"加载Whisper {self.whisper_model_name}模型到{device}设备", extra={"request_id": trace_key})

                # 添加：设置torch环境变量，提高稳定性
                if device == "cuda":
                    # 设置较低的精度以减少内存使用
                    torch.set_float32_matmul_precision('medium')

                model = whisper.load_model(self.whisper_model_name, device=device, download_root=os.path.join(self.temp_dir, "whisper_models"))
                ScriptService._model_cache[model_key] = model
                return model
            except RuntimeError as e:
                # GPU内存不足时回退到CPU
                if "CUDA out of memory" in str(e):
                    logger.warning(f"GPU内存不足，回退到CPU: {str(e)}", extra={"request_id": trace_key})
                    # 尝试加载到 CPU
                    cpu_model_key = f"{self.whisper_model_name}_cpu"
                    if cpu_model_key in ScriptService._model_cache:
                         return ScriptService._model_cache[cpu_model_key]
                    else:
                        model = whisper.load_model(self.whisper_model_name, device="cpu", download_root=os.path.join(self.temp_dir, "whisper_models"))
                        ScriptService._model_cache[cpu_model_key] = model
                        return model

                logger.error(f"Whisper模型加载失败: {str(e)}", exc_info=True, extra={"request_id": trace_key}) # 添加 exc_info=True
                raise AudioTranscriptionError(f"模型加载失败: {str(e)}") from e
            except Exception as e:
                logger.error(f"Whisper模型加载失败: {str(e)}", exc_info=True, extra={"request_id": trace_key}) # 添加 exc_info=True
                raise AudioTranscriptionError(f"模型加载失败: {str(e)}") from e

    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-2")
    @cache_result(expire_seconds=600)
    async def download_audio(self, url: str) -> Tuple[str, str]:
        """
        下载音频并返回文件路径和标题 (代码同前)
        """
        # (此部分代码与之前版本相同，为了简洁省略，假设没有改动)
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()
        logger.info(f"download_audio-开始下载音频: {url}", extra={"request_id": trace_key})
        download_dir = os.path.join(self.temp_dir, f"audio_{int(time.time())}_{trace_key[-6:]}")
        os.makedirs(download_dir, exist_ok=True)
        outtmpl = os.path.join(download_dir, "%(title)s.%(ext)s")
        ydl_opts = {
            'outtmpl': outtmpl, 'format': 'bestaudio/best', 'postprocessors': [], 'quiet': True,
            'noplaylist': True, 'geo_bypass': True, 'socket_timeout': 60, 'retries': 3,
            'http_chunk_size': 10 * 1024 * 1024
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.debug(f"提取音频信息: {url}", extra={"request_id": trace_key})
                info = ydl.extract_info(url, download=True)
                if info is None: raise AudioDownloadError("无法提取音频信息 (info is None)")
                downloaded_path = ydl.prepare_filename(info)
                downloaded_title = info.get('title', "downloaded_audio")
                actual_downloaded_path = None
                if os.path.exists(downloaded_path): actual_downloaded_path = downloaded_path
                else:
                    possible_files = [os.path.join(download_dir, f) for f in os.listdir(download_dir)]
                    if possible_files:
                        actual_downloaded_path = max(possible_files, key=os.path.getctime)
                        logger.warning(f"预期下载路径不存在，使用找到的文件 {actual_downloaded_path}", extra={"request_id": trace_key})
                    else: raise AudioDownloadError(f"下载目录为空: {download_dir}")
                logger.info(f"音频下载完成: {downloaded_title}, 路径: {actual_downloaded_path}", extra={"request_id": trace_key})
                if not actual_downloaded_path or not os.path.exists(actual_downloaded_path): raise AudioDownloadError(f"音频文件未找到: {actual_downloaded_path}")
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
            try: self._cleanup_dir(download_dir, trace_key)
            except Exception as cleanup_e: logger.error(f"下载异常后清理目录失败: {cleanup_e}", extra={"request_id": trace_key})
            raise AudioDownloadError(error_msg) from e

    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-3")
    @cache_result(expire_seconds=300)
    async def transcribe_audio(self, audio_path: str) -> str:
        """
        将音频转写为文本 (已修改DB日志调用方式)

        支持长音频分割并行处理。音频处理完成后会自动删除源文件。

        Args:
            audio_path: 音频文件路径

        Returns:
            str: 转写后的文本

        Raises:
            AudioTranscriptionError: 转写过程中发生错误
        """
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()
        # >>> 修改：安全地获取当前事件循环 <<<
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 在非异步主线程（例如某些后台任务或测试环境）中可能没有运行中的循环
            logger.warning("无法在 transcribe_audio 中获取事件循环，数据库日志可能无法调度", extra={"request_id": trace_key})

        if not os.path.exists(audio_path):
            raise AudioTranscriptionError(f"音频文件不存在: {audio_path}")

        logger.info(f"transcribe_audio-开始转写音频: {audio_path}", extra={"request_id": trace_key})
        start_time = time.time()

        # 音频分割和并行转写
        text = ""
        temp_chunk_paths = [] # 用于收集所有需要清理的临时文件路径

        try:
            # 使用 pydub 加载音频
            try:
                audio = AudioSegment.from_file(audio_path)
            except Exception as load_e:
                 logger.error(f"使用 pydub 加载音频失败: {audio_path}, Error: {load_e}", exc_info=True, extra={"request_id": trace_key})
                 raise AudioTranscriptionError(f"无法加载音频文件: {os.path.basename(audio_path)}") from load_e

            audio_duration = len(audio) / 1000  # 转换为秒

            # 仅在有事件循环时才尝试记录到DB
            if loop:
                try:
                    # 使用 call_soon_threadsafe 调用 info_to_db
                    def _schedule_log(msg, extra_data):
                        try: logger.info_to_db(msg, extra=extra_data)
                        except Exception as e: logger.error(f"调度日志到DB时出错: {e}", exc_info=True)

                    loop.call_soon_threadsafe(_schedule_log, f"音频时长: {audio_duration:.2f}秒", {'request_id': trace_key})
                except Exception as schedule_err:
                    logger.warning(f"调度 '音频时长' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
            else:
                logger.info(f"音频时长: {audio_duration:.2f}秒", extra={'request_id': trace_key}) # 记录到标准日志


            # (积分计算部分代码同前，省略)
            required_points = 0
            duration_seconds = int(audio_duration)
            duration_points = (duration_seconds // 60) * 10
            if duration_seconds % 60 > 0 or duration_seconds == 0: duration_points += 10
            total_required = duration_points
            points_info = request_ctx.get_points_info()
            available_points = points_info.get('available_points', 0)
            if available_points < total_required:
                error_msg = f"提取文案时积分不足: 处理该音频(时长 {duration_seconds} 秒)需要 {total_required} 积分，您当前仅有 {available_points} 积分"
                # 尝试记录积分不足到DB
                if loop:
                     try: loop.call_soon_threadsafe(lambda m, e: logger.info_to_db(m, extra=e), error_msg, {'request_id': trace_key})
                     except Exception as schedule_err: logger.warning(f"调度 '积分不足' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
                else:
                     logger.info(error_msg, extra={'request_id': trace_key}) # 标准日志
                raise AudioTranscriptionError(error_msg)
            # 尝试记录积分检查通过到DB
            if loop:
                 try: loop.call_soon_threadsafe(lambda m, e: logger.info_to_db(m, extra=e), f"提取文案时积分检查通过：所需 {total_required} 积分，可用 {available_points} 积分", {'request_id': trace_key})
                 except Exception as schedule_err: logger.warning(f"调度 '积分通过' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
            else:
                 logger.info(f"提取文案时积分检查通过：所需 {total_required} 积分，可用 {available_points} 积分", extra={'request_id': trace_key})


            # 加载模型
            model = self._get_whisper_model()

            if audio_duration <= 300:  # 5分钟以内直接转写
                logger.info("音频时长小于或等于5分钟，直接转写", extra={"request_id": trace_key})
                # (WAV转换部分同前，省略)
                process_path = audio_path
                try:
                    wav_path = audio_path.replace(os.path.splitext(audio_path)[1], '.wav')
                    if not audio_path.lower().endswith('.wav'):
                        audio.export(wav_path, format="wav")
                        if os.path.exists(wav_path) and os.path.getsize(wav_path) > 100:
                            temp_chunk_paths.append(wav_path)
                            process_path = wav_path
                        else:
                             if os.path.exists(wav_path): self._safe_remove_file(wav_path, trace_key)
                except Exception as export_e: pass # 忽略转换错误

                # 提交转写任务
                # >>> 调试：尝试添加锁 <<<
                # with ScriptService._transcription_lock:
                #     future = ScriptService._thread_pool.submit(...)
                future = ScriptService._thread_pool.submit(
                    lambda p: model.transcribe(p, language="zh", fp16=False), process_path
                )
                try:
                    timeout_duration = max(300, audio_duration * 3)
                    logger.debug(f"设置单文件转写超时时间: {timeout_duration}秒", extra={"request_id": trace_key})
                    result = future.result(timeout=timeout_duration)
                    text = result.get("text", "").strip()
                except FuturesTimeoutError:
                    total_required = 0 # 超时不扣分
                    log_message = f"短音频转写超时({timeout_duration}秒)，不扣分"
                    logger.error(log_message, extra={"request_id": trace_key})
                    # >>> 修改：安全地记录到数据库 <<<
                    if loop:
                        try:
                             # 定义一个包装函数，因为它需要接收参数
                             def _schedule_db_log_safe(msg, extra_data):
                                 try: logger.info_to_db(msg, extra=extra_data) # 在包装器内使用关键字参数
                                 except Exception as e: logger.error(f"调度DB日志时出错(超时包装器): {e}", exc_info=True, extra=extra_data)
                             loop.call_soon_threadsafe(_schedule_db_log_safe, f"转写超时(DB): 短音频({timeout_duration}秒)", {'request_id': trace_key})
                        except Exception as schedule_e:
                             logger.error(f"无法调度超时DB日志: {schedule_e}", extra={"request_id": trace_key})
                    raise AudioTranscriptionError(f"音频转写超时({timeout_duration}秒)，请检查音频文件或稍后重试")
                except Exception as trans_e:
                    total_required = 0 # 转写失败不扣分
                    exc_type = type(trans_e).__name__
                    exc_msg = str(trans_e)
                    log_message = f"短音频转写失败: {exc_type} - {exc_msg}"
                    logger.error(log_message, exc_info=True, extra={"request_id": trace_key})
                     # >>> 修改：安全地记录到数据库 <<<
                    if loop:
                        try:
                             # 使用与上面相同的包装函数模式
                             def _schedule_db_log_safe(msg, extra_data):
                                 try: logger.info_to_db(msg, extra=extra_data)
                                 except Exception as e: logger.error(f"调度DB日志时出错(短音频失败包装器): {e}", exc_info=True, extra=extra_data)
                             db_log_msg = f"转写失败(DB): 短音频. 类型: {exc_type}, 消息: '{exc_msg}'"
                             loop.call_soon_threadsafe(_schedule_db_log_safe, db_log_msg, {'request_id': trace_key})
                        except Exception as schedule_e:
                             logger.error(f"无法调度短音频失败DB日志: {schedule_e}", extra={"request_id": trace_key})
                    raise AudioTranscriptionError(f"音频转写失败: {exc_type}") from trans_e


            else: # 音频时长 > 5分钟，进行分割和并行处理
                # (音频分割部分代码同前，省略)
                optimal_chunk_duration = min(max(100, int(audio_duration / 40)), 180)
                chunk_duration = optimal_chunk_duration if optimal_chunk_duration != self.chunk_duration else self.chunk_duration
                num_chunks = int(audio_duration // chunk_duration) + (1 if audio_duration % chunk_duration != 0 else 0)
                logger.info(f"音频将被分割为 {num_chunks} 个片段 (每段约 {chunk_duration} 秒) 进行并行处理", extra={"request_id": trace_key})
                chunk_dir = os.path.join(self.temp_dir, f"chunks_{int(time.time())}_{trace_key[-6:]}")
                os.makedirs(chunk_dir, exist_ok=True)
                temp_chunk_paths.append(chunk_dir)
                chunk_files = []
                for chunk_idx in range(num_chunks):
                    start_ms = chunk_idx * chunk_duration * 1000
                    end_ms = min((chunk_idx + 1) * chunk_duration * 1000, len(audio))
                    if end_ms <= start_ms: continue
                    chunk_format = "wav"
                    chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_idx}.{chunk_format}")
                    try:
                        chunk_audio = audio[start_ms:end_ms]
                        if len(chunk_audio) < 100: continue
                        chunk_audio.export(chunk_path, format=chunk_format)
                        if not os.path.exists(chunk_path) or os.path.getsize(chunk_path) < 100:
                            if os.path.exists(chunk_path): self._safe_remove_file(chunk_path, trace_key)
                            continue
                        temp_chunk_paths.append(chunk_path)
                        chunk_files.append((chunk_idx, chunk_path, len(chunk_audio) / 1000.0))
                    except Exception as export_e:
                         logger.error(f"导出音频片段 {chunk_idx+1}/{num_chunks} 失败: {export_e}", exc_info=True, extra={"request_id": trace_key})
                         if os.path.exists(chunk_path): self._safe_remove_file(chunk_path, trace_key)
                         continue
                del audio
                import gc
                gc.collect()

                # >>> 修改：process_chunk 现在接受 loop 参数 <<<
                def process_chunk(chunk_data: tuple, loop: Optional[asyncio.AbstractEventLoop]) -> tuple[int, str]:
                    chunk_idx, chunk_path, chunk_duration_sec = chunk_data
                    nonlocal total_required

                    # >>> 定义用于安全调度DB日志的包装函数 <<<
                    # 这个函数将在主事件循环线程中被执行
                    def _schedule_db_log_safe(msg: str, extra_data: dict):
                        try:
                            # 在这里调用原始的 logger 方法，可以安全使用 kwargs
                            logger.info_to_db(msg, extra=extra_data)
                        except Exception as e:
                            # 记录在调度执行过程中发生的错误
                            # 注意：这里的 logger.error 本身如果也触发异步DB日志，可能会再次遇到问题
                            # 最好的解决办法还是让 logger 的DB处理器本身线程安全
                            logger.error(f"调度DB日志时出错(包装器内): {e}", exc_info=True, extra=extra_data)


                    try:
                        logger.debug(f"开始转写片段 {chunk_idx+1}/{num_chunks}", extra={"request_id": trace_key})

                        if not os.path.exists(chunk_path) or os.path.getsize(chunk_path) < 100:
                            logger.error(f"片段 {chunk_idx+1}/{num_chunks} 文件无效或不存在于转写前", extra={"request_id": trace_key})
                            return chunk_idx, ""

                        # >>> 调试：尝试添加锁 <<<
                        # with ScriptService._transcription_lock:
                        #     future = ScriptService._thread_pool.submit(...)
                        future = ScriptService._thread_pool.submit(
                            lambda p: model.transcribe(
                                p, language="zh", task="transcribe", fp16=False
                            ), chunk_path
                        )
                        timeout_chunk = max(180, chunk_duration_sec * 4)
                        logger.debug(f"设置片段 {chunk_idx+1} 转写超时时间: {timeout_chunk}秒", extra={"request_id": trace_key})
                        result = future.result(timeout=timeout_chunk)
                        chunk_text = result.get("text", "").strip()
                        logger.debug(f"片段 {chunk_idx+1}/{num_chunks} 转写完成", extra={"request_id": trace_key})
                        return chunk_idx, chunk_text

                    except FuturesTimeoutError:
                        total_required = 0
                        log_message = f"片段 {chunk_idx+1}/{num_chunks} 转写超时({timeout_chunk}秒), 不扣分"
                        # 1. 标准日志记录（同步，到控制台/文件）
                        logger.error(log_message, extra={"request_id": trace_key})

                        # 2. >>> 修改：使用 call_soon_threadsafe 安全调度DB日志 <<<
                        if loop:
                            try:
                                db_log_msg = f"转写超时(DB): 片段 {chunk_idx+1}/{num_chunks} ({timeout_chunk}秒)"
                                log_extra = {'request_id': trace_key}
                                # 调用包装函数，传递位置参数
                                loop.call_soon_threadsafe(_schedule_db_log_safe, db_log_msg, log_extra)
                            except Exception as schedule_e:
                                logger.error(f"无法调度超时DB日志: {schedule_e}", extra={"request_id": trace_key})
                        return chunk_idx, ""

                    except Exception as e:
                        total_required = 0
                        exc_type = type(e).__name__
                        exc_msg = str(e)
                        log_message = f"片段 {chunk_idx+1}/{num_chunks} 转写失败, 不扣分. 类型: {exc_type}, 消息: '{exc_msg}'"
                        # 1. 标准日志记录（同步，到控制台/文件），包含traceback
                        logger.error(log_message, exc_info=True, extra={"request_id": trace_key})

                        # 2. >>> 修改：使用 call_soon_threadsafe 安全调度DB日志 <<<
                        if loop:
                             try:
                                 db_log_msg = f"转写错误(DB): 片段 {chunk_idx+1}/{num_chunks}. 类型: {exc_type}. 消息: '{exc_msg}'"
                                 log_extra = {'request_id': trace_key}
                                 # 调用包装函数，传递位置参数
                                 loop.call_soon_threadsafe(_schedule_db_log_safe, db_log_msg, log_extra)
                             except Exception as schedule_e:
                                 logger.error(f"无法调度转写失败DB日志: {schedule_e}", extra={"request_id": trace_key})
                        return chunk_idx, ""

                # (后续处理部分代码同前，但修改了 submit 调用方式)
                if not chunk_files: raise AudioTranscriptionError("无法生成有效的音频片段，请检查音频文件")
                workers = min(self.max_parallel_chunks, len(chunk_files), max(2, (os.cpu_count() or 4) // 2))
                logger.info(f"使用 {workers} 个并行任务进行转写", extra={"request_id": trace_key})

                futures_map = {}
                results_list = [""] * num_chunks

                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"audio_{trace_key[-6:]}") as local_executor:
                    for chunk_data in chunk_files:
                        chunk_idx = chunk_data[0]
                        # >>> 修改：将 loop 传递给 process_chunk <<<
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
            # 尝试记录完成日志到DB
            if loop:
                try: loop.call_soon_threadsafe(lambda m, e: logger.info_to_db(m, extra=e), f"音频转写完成，耗时: {elapsed_time:.2f}秒", {'request_id': trace_key})
                except Exception as schedule_err: logger.warning(f"调度 '转写完成' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
            else:
                logger.info(f"音频转写完成，耗时: {elapsed_time:.2f}秒", extra={'request_id': trace_key})


            # 只有在所有步骤成功（total_required 未被置零）的情况下才设置消耗积分
            if total_required > 0:
                request_ctx.set_consumed_points(total_required, "音频转写服务")
                # 尝试记录积分消耗到DB
                if loop:
                    try: loop.call_soon_threadsafe(lambda m, e: logger.info_to_db(m, extra=e), f"成功完成转写，消耗积分: {total_required}", {'request_id': trace_key})
                    except Exception as schedule_err: logger.warning(f"调度 '消耗积分' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
                else:
                     logger.info(f"成功完成转写，消耗积分: {total_required}", extra={'request_id': trace_key})
            else:
                request_ctx.set_consumed_points(0)
                 # 尝试记录未消耗积分到DB
                if loop:
                    try: loop.call_soon_threadsafe(lambda m, e: logger.info_to_db(m, extra=e), "转写过程中发生错误，未消耗积分", {'request_id': trace_key})
                    except Exception as schedule_err: logger.warning(f"调度 '未消耗积分' DB日志失败: {schedule_err}", extra={'request_id': trace_key})
                else:
                    logger.info("转写过程中发生错误，未消耗积分", extra={'request_id': trace_key})

            return text

        except AudioTranscriptionError as ate:
            # 捕获我们自己定义的错误，确保积分设置为0
            request_ctx.set_consumed_points(0)
            # 错误信息应该已在发生点记录，这里只重新抛出
            raise ate
        except Exception as e:
            # 捕获其他意外错误
            request_ctx.set_consumed_points(0)
            error_msg = f"音频转写过程中发生未知严重错误: {type(e).__name__} - {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            # 尝试异步记录这个顶层错误到数据库
            if loop:
                 try:
                     # 使用包装函数记录顶层错误
                     def _schedule_db_log_safe(msg, extra_data):
                         try: logger.info_to_db(msg, extra=extra_data)
                         except Exception as e_inner: logger.error(f"调度DB日志时出错(顶层错误包装器): {e_inner}", exc_info=True, extra=extra_data)
                     db_log_msg = f"转写顶层错误(DB): {type(e).__name__} - {str(e)}"
                     loop.call_soon_threadsafe(_schedule_db_log_safe, db_log_msg, {'request_id': trace_key})
                 except Exception as log_e:
                     logger.error(f"无法调度顶层错误的异步DB日志: {log_e}", extra={"request_id": trace_key})

            raise AudioTranscriptionError(error_msg) from e
        finally:
            # (清理部分代码同前，省略)
            logger.debug(f"开始清理临时文件: {temp_chunk_paths}", extra={"request_id": trace_key})
            paths_to_clean = sorted(temp_chunk_paths, key=lambda p: os.path.isfile(p), reverse=True)
            for path_to_clean in paths_to_clean:
                if os.path.isfile(path_to_clean): self._safe_remove_file(path_to_clean, trace_key)
                elif os.path.isdir(path_to_clean): self._cleanup_dir(path_to_clean, trace_key)
            original_audio_in_temp = any(os.path.samefile(audio_path, p) for p in temp_chunk_paths if os.path.exists(p) and os.path.isfile(p))
            if not original_audio_in_temp and os.path.exists(audio_path): self._safe_remove_file(audio_path, trace_key)
            self._cleanup_parent_dir(audio_path, trace_key)

    # ( _safe_remove_file, _cleanup_dir, _cleanup_parent_dir 方法同前，省略 )
    def _safe_remove_file(self, file_path: str, trace_key: str) -> None:
        try:
            if os.path.exists(file_path) and os.path.isfile(file_path):
                os.remove(file_path)
                logger.debug(f"已删除文件: {file_path}", extra={"request_id": trace_key})
        except Exception as e:
            logger.warning(f"删除文件失败 {file_path}: {type(e).__name__} - {str(e)}", extra={"request_id": trace_key})

    def _cleanup_dir(self, dir_path: str, trace_key: str) -> None:
        try:
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                logger.debug(f"开始清理目录: {dir_path}", extra={"request_id": trace_key})
                for item in os.listdir(dir_path):
                    item_path = os.path.join(dir_path, item)
                    if os.path.isfile(item_path):
                        self._safe_remove_file(item_path, trace_key)
                try:
                     os.rmdir(dir_path)
                     logger.debug(f"已删除空目录: {dir_path}", extra={"request_id": trace_key})
                except OSError as e:
                     logger.warning(f"删除目录失败（可能非空） {dir_path}: {e}", extra={"request_id": trace_key})
        except Exception as e:
            logger.warning(f"清理目录时发生错误 {dir_path}: {type(e).__name__} - {str(e)}", extra={"request_id": trace_key})

    def _cleanup_parent_dir(self, file_path: str, trace_key: str) -> None:
        try:
            parent_dir = os.path.dirname(file_path)
            if parent_dir and os.path.exists(parent_dir) and parent_dir != self.temp_dir and parent_dir != os.path.abspath(os.sep):
                if not os.listdir(parent_dir):
                    self._cleanup_dir(parent_dir, trace_key)
        except Exception as e:
            logger.debug(f"尝试清理父目录失败: {parent_dir}, Error: {str(e)}", extra={"request_id": trace_key})


    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-2")
    @cache_result(expire_seconds=600)
    async def download_audio_direct(self, url: str) -> Tuple[str, str]:
        """
        直接从URL下载音频文件并返回文件路径和文件名 (代码同前)
        """
        # (此部分代码与之前版本相同，为了简洁省略，假设使用 httpx 且没有改动)
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()
        logger.info(f"download_audio_direct-开始直接下载音频: {url}", extra={"request_id": trace_key})
        download_dir = os.path.join(self.temp_dir, f"audio_direct_{int(time.time())}_{trace_key[-6:]}")
        os.makedirs(download_dir, exist_ok=True)
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            file_name = os.path.basename(parsed_url.path)
            if not file_name or '.' not in file_name: file_name = f"audio_{int(time.time())}.audio"
        except Exception: file_name = f"audio_{int(time.time())}.audio"
        downloaded_path = os.path.join(download_dir, file_name)
        try:
            import httpx
            headers = {'User-Agent': 'Mozilla/5.0 ...', 'Accept': 'audio/...', 'Accept-Language': 'en-US,en;q=0.9', 'Referer': url}
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=60.0) as client:
                async with client.stream("GET", url) as response:
                    content_disposition = response.headers.get('Content-Disposition')
                    if content_disposition:
                        import re; from urllib.parse import unquote
                        fname_match = re.search(r'filename\*?=(?:UTF-8\'\')?([^;]+)', content_disposition, re.IGNORECASE)
                        if fname_match:
                            potential_name = unquote(fname_match.group(1).strip('" '))
                            if '.' in potential_name:
                                file_name = os.path.basename(potential_name)
                                downloaded_path = os.path.join(download_dir, file_name)
                    response.raise_for_status()
                    content_type = response.headers.get('Content-Type', '').lower()
                    if not content_type.startswith(('audio/', 'video/', 'application/octet-stream', 'application/ogg')): logger.warning(f"下载内容类型可能不是音频: {content_type}", extra={"request_id": trace_key})
                    bytes_downloaded = 0
                    try:
                        with open(downloaded_path, 'wb') as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                if chunk: f.write(chunk); bytes_downloaded += len(chunk)
                    except Exception as write_e: raise AudioDownloadError(f"写入文件时出错: {write_e}") from write_e
                    if bytes_downloaded == 0 and response.status_code == 200: logger.warning(f"下载成功但文件大小为 0: {downloaded_path}", extra={"request_id": trace_key})
            if not os.path.exists(downloaded_path):
                possible_files = [os.path.join(download_dir, f) for f in os.listdir(download_dir)]
                if len(possible_files) == 1: downloaded_path = possible_files[0]; file_name = os.path.basename(downloaded_path)
                else: raise AudioDownloadError(f"音频文件未找到: {downloaded_path}")
            if os.path.getsize(downloaded_path) == 0:
                self._safe_remove_file(downloaded_path, trace_key); raise AudioDownloadError(f"下载的音频文件为空: {downloaded_path}")
            logger.info(f"音频直接下载完成: {file_name}", extra={"request_id": trace_key})
            return downloaded_path, file_name
        except httpx.HTTPStatusError as e: error_msg = f"下载失败 (HTTP Status {e.response.status_code}): {e.request.url}"; logger.error(error_msg, extra={"request_id": trace_key}); self._cleanup_dir(download_dir, trace_key); raise AudioDownloadError(error_msg) from e
        except httpx.RequestError as e: error_msg = f"下载失败 (Request Error): {type(e).__name__} - {e.request.url}"; logger.error(error_msg, extra={"request_id": trace_key}); self._cleanup_dir(download_dir, trace_key); raise AudioDownloadError(error_msg) from e
        except AudioDownloadError: raise
        except Exception as e: error_msg = f"直接下载时未知异常: {type(e).__name__} - {str(e)}"; logger.error(error_msg, exc_info=True, extra={"request_id": trace_key}); self._cleanup_dir(download_dir, trace_key); raise AudioDownloadError(error_msg) from e