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
        
        try:
            logger.info(f"加载Whisper {self.whisper_model_name}模型到{device}设备", extra={"request_id": trace_key})
            self.whisper_model = whisper.load_model(self.whisper_model_name, device=device)
            return self.whisper_model
        except RuntimeError as e:
            # GPU内存不足时回退到CPU
            if "CUDA out of memory" in str(e):
                logger.warning(f"GPU内存不足，回退到CPU: {str(e)}", extra={"request_id": trace_key})
                self.whisper_model = whisper.load_model(self.whisper_model_name, device="cpu")
                return self.whisper_model
            
            logger.error(f"Whisper模型加载失败: {str(e)}", extra={"request_id": trace_key})
            raise AudioTranscriptionError(f"模型加载失败: {str(e)}") from e
        except Exception as e:
            logger.error(f"Whisper模型加载失败: {str(e)}", extra={"request_id": trace_key})
            raise AudioTranscriptionError(f"模型加载失败: {str(e)}") from e
    
    @gate_keeper()
    @log_service_call(method_type="script", tollgate="10-2")
    @cache_result(expire_seconds=3600)
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
    @cache_result(expire_seconds=3600)
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
            
            logger.info(f"音频时长: {audio_duration:.2f}秒", extra={"request_id": trace_key})
            
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
                error_msg = f"积分不足: 处理该音频(时长 {duration_seconds} 秒)需要 {total_required} 积分（基础：{required_points}，时长：{duration_points}），您当前仅有 {available_points} 积分"
                logger.warning(error_msg, extra={"request_id": trace_key})
                raise AudioTranscriptionError(error_msg)
            
            logger.info(f"积分检查通过：所需 {total_required} 积分，可用 {available_points} 积分", 
                    extra={"request_id": trace_key})
            
            # 加载模型
            model = self._get_whisper_model()
            
            if audio_duration <= 1800:  # 30分钟以内直接转写
                logger.info("音频时长小于30分钟，直接转写", extra={"request_id": trace_key})
                result = model.transcribe(audio_path)
                text = result.get("text", "").strip()
                
            else:
                # 音频分割和并行转写
                num_chunks = int(audio_duration // self.chunk_duration) + (
                    1 if audio_duration % self.chunk_duration != 0 else 0
                )
                
                logger.info(f"音频将被分割为{num_chunks}个片段进行并行处理", extra={"request_id": trace_key})
                
                # 创建临时目录存储切割后的音频片段
                chunk_dir = os.path.join(self.temp_dir, f"chunks_{int(time.time())}")
                os.makedirs(chunk_dir, exist_ok=True)
                
                # 处理单个音频片段
                def process_chunk(chunk_idx: int) -> str:
                    start_ms = chunk_idx * self.chunk_duration * 1000
                    end_ms = min((chunk_idx + 1) * self.chunk_duration * 1000, len(audio))
                    
                    chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_idx}.mp3")
                    temp_chunk_paths.append(chunk_path)
                    
                    # 分割并保存音频片段
                    chunk_audio = audio[start_ms:end_ms]
                    chunk_audio.export(chunk_path, format="mp3")
                    
                    try:
                        logger.debug(f"开始转写片段 {chunk_idx+1}/{num_chunks}", extra={"request_id": trace_key})
                        result = model.transcribe(chunk_path)
                        chunk_text = result.get("text", "").strip()
                        logger.debug(f"片段 {chunk_idx+1}/{num_chunks} 转写完成", extra={"request_id": trace_key})
                        return chunk_text
                    except Exception as e:
                        logger.error(f"片段 {chunk_idx+1}/{num_chunks} 转写失败: {str(e)}", extra={"request_id": trace_key})
                        return ""
                
                # 使用线程池并行处理音频片段
                with ThreadPoolExecutor(max_workers=self.max_parallel_chunks) as executor:
                    results = list(executor.map(process_chunk, range(num_chunks)))
                    
                # 合并结果
                text = "\n".join(filter(None, results))
                logger.info("所有音频片段转写完成", extra={"request_id": trace_key})
            
            elapsed_time = time.time() - start_time
            logger.info(f"音频转写完成，耗时: {elapsed_time:.2f}秒", extra={"request_id": trace_key})
            
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