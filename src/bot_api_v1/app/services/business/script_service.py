"""
音频转写脚本服务模块

提供音频下载、转写和处理相关功能。
"""
import os
import time
import tempfile
from typing import Tuple, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor, as_completed  # 在顶部导入as_completed
import torch
import whisper
import yt_dlp
from pydub import AudioSegment

from bot_api_v1.app.core.cache import cache_result

# 导入项目日志模块
from bot_api_v1.app.core.logger import logger
# 导入服务日志装饰器
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
    # 添加类级别的模型缓存和线程池
    _model_cache = {}  # 类变量，用于缓存不同设备上的不同模型
    _thread_pool = None  # 类变量，共享线程池
    _max_concurrent_tasks = 20  # 最大并发任务数
    _model_lock = None  # 模型加载锁

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
    
    def _get_whisper_model(self) -> Any:
        """
        加载Whisper模型，如果CUDA可用则使用GPU
        
        Returns:
            加载的Whisper模型实例
        
        Raises:
            AudioTranscriptionError: 模型加载失败
        """
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
                model = whisper.load_model(self.whisper_model_name, device=device)
                ScriptService._model_cache[model_key] = model
                return model
            except RuntimeError as e:
                # GPU内存不足时回退到CPU
                if "CUDA out of memory" in str(e):
                    logger.warning(f"GPU内存不足，回退到CPU: {str(e)}", extra={"request_id": trace_key})
                    model = whisper.load_model(self.whisper_model_name, device="cpu")
                    ScriptService._model_cache[f"{self.whisper_model_name}_cpu"] = model
                    return model
                
                logger.error(f"Whisper模型加载失败: {str(e)}", extra={"request_id": trace_key})
                raise AudioTranscriptionError(f"模型加载失败: {str(e)}") from e
            except Exception as e:
                logger.error(f"Whisper模型加载失败: {str(e)}", extra={"request_id": trace_key})
                raise AudioTranscriptionError(f"模型加载失败: {str(e)}") from e
    
    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-2")
    @cache_result(expire_seconds=600)
    async def download_audio(self, url: str) -> Tuple[str, str]:
        """
        下载音频并返回文件路径和标题
        
        Args:
            url: 要下载的音频URL
            
        Returns:
            Tuple[str, str]: (文件路径, 标题)
            
        Raises:
            AudioDownloadError: 下载失败时抛出
        """
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()
        
        # logger.info(f"download_audio start: {url}", extra={"request_id": trace_key})

        # 使用trace_key记录日志
        logger.info(f"download_audio-开始下载音频: {url}", extra={"request_id": trace_key})
        
        # 创建唯一的临时目录
        download_dir = os.path.join(self.temp_dir, f"audio_{int(time.time())}")
        os.makedirs(download_dir, exist_ok=True)
        
        outtmpl = os.path.join(download_dir, "%(title)s.%(ext)s")
        
        ydl_opts = {
            'outtmpl': outtmpl,
            'format': 'bestaudio/best',
            'postprocessors': [],  # 禁用所有后处理器
            'quiet': True,         # 减少输出
            'noplaylist': True,    # 不下载播放列表
            'geo_bypass': True,    # 尝试绕过地理限制
            'socket_timeout': 30,  # 设置超时时间
            'retries': 3,          # 重试次数
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.debug(f"提取音频信息: {url}", extra={"request_id": trace_key})
                info = ydl.extract_info(url, download=True)
                
                if info is None:
                    raise AudioDownloadError("无法提取音频信息")
                
                downloaded_path = ydl.prepare_filename(info)
                downloaded_title = info.get('title', "downloaded_audio")
                
                logger.info(f"音频下载完成: {downloaded_title}", extra={"request_id": trace_key})
                
                # 验证文件是否存在且不为空
                if not os.path.exists(downloaded_path):
                    raise AudioDownloadError(f"音频文件未找到: {downloaded_path}")
                    
                if os.path.getsize(downloaded_path) == 0:
                    os.remove(downloaded_path)
                    raise AudioDownloadError(f"下载的音频文件为空: {downloaded_path}")
                
                return downloaded_path, downloaded_title
                
        except yt_dlp.utils.DownloadError as e:
            error_msg = f"下载音频失败: {str(e)}"
            logger.error(error_msg, extra={"request_id": trace_key})
            self._cleanup_dir(download_dir, trace_key)
            raise AudioDownloadError(error_msg) from e
            
        except Exception as e:
            error_msg = f"下载音频时出现异常: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            self._cleanup_dir(download_dir, trace_key)
            raise AudioDownloadError(error_msg) from e
    
    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-3")
    @cache_result(expire_seconds=300)
    async def transcribe_audio(self, audio_path: str) -> str:
        """
        将音频转写为文本
        
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
        
        if not os.path.exists(audio_path):
            raise AudioTranscriptionError(f"音频文件不存在: {audio_path}")
        
        logger.info(f"transcribe_audio-开始转写音频: {audio_path}", extra={"request_id": trace_key})
        start_time = time.time()
        
        # 音频分割和并行转写
        text = ""
        temp_chunk_paths = []
        
        try:
            # 使用 pydub 加载音频
            audio = AudioSegment.from_file(audio_path)
            audio_duration = len(audio) / 1000  # 转换为秒
            
            logger.info_to_db(f"音频时长: {audio_duration:.2f}秒", extra={"request_id": trace_key})
            
            # 计算所需积分：按时长计算，每60秒10分，不足60秒按10分计算
            required_points = 0  # 不额外计算基础消耗
            duration_seconds = int(audio_duration)
            duration_points = (duration_seconds // 60) * 10  # 完整分钟数
            if duration_seconds % 60 > 0:
                duration_points += 10  # 不足60秒的部分也算10分

            total_required = duration_points  # 总积分就是时长积分
            
            # 从上下文获取积分信息
            points_info = request_ctx.get_points_info()
            available_points = points_info.get('available_points', 0)
            
            # 验证积分是否足够
            if available_points < total_required:
                error_msg = f"提取文案时积分不足: 处理该音频(时长 {duration_seconds} 秒)需要 {total_required} 积分（基础：{required_points}，时长：{duration_points}），您当前仅有 {available_points} 积分"
                logger.info_to_db(error_msg, extra={"request_id": trace_key})
                raise AudioTranscriptionError(error_msg)
            
            logger.info_to_db(f"提取文案时积分检查通过：所需 {total_required} 积分，可用 {available_points} 积分", 
                    extra={"request_id": trace_key})
            
            # 加载模型
            model = self._get_whisper_model()
            
            if audio_duration <= 300:  # 5分钟以内直接转写
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
                
            else:
                # 音频分割和并行转写
                # 动态调整分片大小，避免过多小片段
                optimal_chunk_duration = min(max(100, int(audio_duration / 40)), 180)
                chunk_duration = optimal_chunk_duration if optimal_chunk_duration != self.chunk_duration else self.chunk_duration
                
                num_chunks = int(audio_duration // chunk_duration) + (
                    1 if audio_duration % chunk_duration != 0 else 0
                )
                
                logger.info(f"音频将被分割为{num_chunks}个片段(每段{chunk_duration}秒)进行并行处理", extra={"request_id": trace_key})
            
                # 创建临时目录存储切割后的音频片段
                chunk_dir = os.path.join(self.temp_dir, f"chunks_{int(time.time())}")
                os.makedirs(chunk_dir, exist_ok=True)

                # 预先分割所有音频片段，避免在线程中重复加载大音频文件
                chunk_files = []
                for chunk_idx in range(num_chunks):
                    start_ms = chunk_idx * chunk_duration * 1000
                    end_ms = min((chunk_idx + 1) * chunk_duration * 1000, len(audio))
                    
                    chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_idx}.mp3")
                    temp_chunk_paths.append(chunk_path)
                    
                    # 分割并保存音频片段
                    chunk_audio = audio[start_ms:end_ms]
                    chunk_audio.export(chunk_path, format="mp3")
                    chunk_files.append((chunk_idx, chunk_path))

                # 释放原始音频内存
                del audio
                import gc
                gc.collect()  # 强制垃圾回收
                
                # 处理单个音频片段
                def process_chunk(chunk_data: tuple) -> str:
                    chunk_idx, chunk_path = chunk_data
                    
                    try:
                        logger.debug(f"开始转写片段 {chunk_idx+1}/{num_chunks}", extra={"request_id": trace_key})
                        # 使用共享线程池处理，而不是在当前线程处理
                        future = ScriptService._thread_pool.submit(
                            lambda: model.transcribe(chunk_path, language="zh", task="transcribe")
                        )
                        # 设置合理的超时时间
                        result = future.result(timeout=max(180, chunk_duration * 2))
                        chunk_text = result.get("text", "").strip()
                        logger.debug(f"片段 {chunk_idx+1}/{num_chunks} 转写完成", extra={"request_id": trace_key})
                        return chunk_text
                    except concurrent.futures.TimeoutError:
                        logger.error(f"片段 {chunk_idx+1}/{num_chunks} 转写超时", extra={"request_id": trace_key})
                        return ""
                    except Exception as e:
                        logger.error(f"片段 {chunk_idx+1}/{num_chunks} 转写失败: {str(e)}", extra={"request_id": trace_key})
                        return ""
                
                # 限制当前请求的并行度，避免单个请求占用过多资源
                workers = min(self.max_parallel_chunks, num_chunks, max(2, (os.cpu_count() or 4) // 2))
                logger.info(f"使用{workers}个并行任务进行转写", extra={"request_id": trace_key})
                
                # 创建本地线程池，控制单个请求的并行度
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"audio_{trace_key[-6:]}") as local_executor:
                    futures = [local_executor.submit(process_chunk, chunk_data) for chunk_data in chunk_files]
                    results = []
                    
                    # 使用as_completed获取先完成的结果，提高整体响应速度
                    for future in as_completed(futures):
                        results.append(future.result())
                    
                # 合并结果，保持段落顺序（需要重新排序，因为as_completed返回的顺序不确定）
                sorted_results = [""] * len(chunk_files)
                for i, future in enumerate(futures):
                    if future.done():
                        chunk_idx = chunk_files[i][0]
                        sorted_results[chunk_idx] = future.result()
                
                text = "\n".join(filter(None, sorted_results))
                logger.info("所有音频片段转写完成", extra={"request_id": trace_key})

            elapsed_time = time.time() - start_time
            logger.info_to_db(f"音频转写完成，耗时: {elapsed_time:.2f}秒", extra={"request_id": trace_key})
            
            # 设置消耗的积分
            request_ctx.set_consumed_points(total_required, "音频转写服务")
            
            return text
            
        except AudioTranscriptionError:
            # 重新抛出自定义错误，不消耗积分
            request_ctx.set_consumed_points(0)
            raise
        except Exception as e:
            # 确保失败时不消耗积分
            request_ctx.set_consumed_points(0)
            error_msg = f"音频转写失败: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            raise AudioTranscriptionError(error_msg) from e
        finally:
            # 清理临时音频片段
            for chunk_path in temp_chunk_paths:
                self._safe_remove_file(chunk_path, trace_key)
            
            # 删除原始音频文件
            self._safe_remove_file(audio_path, trace_key)
            
            # 尝试删除可能的空目录
            self._cleanup_parent_dir(audio_path, trace_key)
    
    def _safe_remove_file(self, file_path: str, trace_key: str) -> None:
        """
        安全删除文件，忽略错误
        
        Args:
            file_path: 要删除的文件路径
            trace_key: 请求跟踪ID
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"已删除文件: {file_path}", extra={"request_id": trace_key})
        except Exception as e:
            logger.warning(f"删除文件失败 {file_path}: {str(e)}", extra={"request_id": trace_key})
    
    def _cleanup_dir(self, dir_path: str, trace_key: str) -> None:
        """
        清理目录及其内容
        
        Args:
            dir_path: 要清理的目录路径
            trace_key: 请求跟踪ID
        """
        try:
            if os.path.exists(dir_path):
                for item in os.listdir(dir_path):
                    item_path = os.path.join(dir_path, item)
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                os.rmdir(dir_path)
                logger.debug(f"已清理目录: {dir_path}", extra={"request_id": trace_key})
        except Exception as e:
            logger.warning(f"清理目录失败 {dir_path}: {str(e)}", extra={"request_id": trace_key})
    
    def _cleanup_parent_dir(self, file_path: str, trace_key: str) -> None:
        """
        尝试清理文件所在的父目录(如果为空)
        
        Args:
            file_path: 文件路径
            trace_key: 请求跟踪ID
        """
        try:
            parent_dir = os.path.dirname(file_path)
            if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                os.rmdir(parent_dir)
                logger.debug(f"已删除空目录: {parent_dir}", extra={"request_id": trace_key})
        except Exception as e:
            logger.warning(f"删除目录失败: {str(e)}", extra={"request_id": trace_key})



    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-2")
    @cache_result(expire_seconds=600)
    async def download_audio_direct(self, url: str) -> Tuple[str, str]:
        """
        直接从URL下载音频文件并返回文件路径和文件名
        
        适用于直接音频文件URL（如mp3、wav等），不需要通过yt-dlp提取
        
        Args:
            url: 要下载的音频直链URL
            
        Returns:
            Tuple[str, str]: (文件路径, 文件名)
            
        Raises:
            AudioDownloadError: 下载失败时抛出
        """
        # 获取trace_key
        trace_key = request_ctx.get_trace_key()
        
        logger.info(f"download_audio_direct-开始直接下载音频: {url}", extra={"request_id": trace_key})
        
        # 创建唯一的临时目录
        download_dir = os.path.join(self.temp_dir, f"audio_direct_{int(time.time())}")
        os.makedirs(download_dir, exist_ok=True)
        
        # 从URL中提取文件名
        file_name = url.split('/')[-1]
        if not file_name or '.' not in file_name:
            # 如果无法从URL获取有效文件名，使用时间戳生成
            file_name = f"audio_{int(time.time())}.mp3"
        
        downloaded_path = os.path.join(download_dir, file_name)
        
        try:
            import requests
            
            # 设置请求头，模拟浏览器行为
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
            }
            
            # 使用流式下载以处理大文件
            with requests.get(url, headers=headers, stream=True, timeout=30) as response:
                response.raise_for_status()  # 确保请求成功
                
                # 获取内容类型，验证是否为音频文件
                content_type = response.headers.get('Content-Type', '')
                if not content_type.startswith(('audio/', 'video/', 'application/octet-stream')):
                    logger.warning(f"下载的内容可能不是音频文件，Content-Type: {content_type}", 
                                  extra={"request_id": trace_key})
                
                # 写入文件
                with open(downloaded_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            # 验证文件是否存在且不为空
            if not os.path.exists(downloaded_path):
                raise AudioDownloadError(f"音频文件未找到: {downloaded_path}")
                
            if os.path.getsize(downloaded_path) == 0:
                os.remove(downloaded_path)
                raise AudioDownloadError(f"下载的音频文件为空: {downloaded_path}")
            
            logger.info(f"音频直接下载完成: {file_name}", extra={"request_id": trace_key})
            return downloaded_path, file_name
            
        except requests.RequestException as e:
            error_msg = f"下载音频失败: {str(e)}"
            logger.error(error_msg, extra={"request_id": trace_key})
            self._cleanup_dir(download_dir, trace_key)
            raise AudioDownloadError(error_msg) from e
            
        except Exception as e:
            error_msg = f"下载音频时出现异常: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={"request_id": trace_key})
            self._cleanup_dir(download_dir, trace_key)
            raise AudioDownloadError(error_msg) from e