"""
日志系统模块

提供全局日志记录功能，使用loguru增强日志展示，支持请求上下文和链路追踪。
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

from loguru import logger as loguru_logger
from colorama import init as colorama_init
from dotenv import load_dotenv

from bot_api_v1.app.core.context import request_ctx

# 初始化colorama，确保在Windows平台上也能正确显示颜色
colorama_init()

# 加载环境变量
load_dotenv()

# 移除默认的loguru处理器
loguru_logger.remove()


def setup_logger():
    """初始化并配置logger"""
    # 获取环境变量
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    environment = os.getenv("ENVIRONMENT", "development").lower()
    
    # 设置日志目录
    log_dir = Path(os.getenv("LOG_DIR", Path(__file__).parent.parent / "logs"))
    try:
        log_dir.mkdir(exist_ok=True)
    except Exception as e:
        print(f"无法创建日志目录: {e}")
        raise
    
    # 添加控制台输出处理器
    loguru_logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <blue>[{extra[request_id]}]</blue> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )
    
    # 添加文件处理器
    loguru_logger.add(
        log_dir / "api.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | [{extra[request_id]}] | {level: <8} | {name}:{function} | {message}",
        level=log_level,
        rotation="00:00",  # 每天午夜轮转
        compression="gz",  # 使用gzip压缩
        retention="30 days",  # 保留30天
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )
    
    return loguru_logger.bind(request_id="system")


class LoggerInterface:
    """日志接口封装，提供与原标准logger兼容的方法"""
    
    def __init__(self, logger_instance):
        self._logger = logger_instance
    
    def debug(self, msg, *args, **kwargs):
        """记录DEBUG级别日志"""
        extra = self._get_extra(kwargs)
        self._logger.bind(**extra).debug(msg)
    
    def info(self, msg, *args, **kwargs):
        """记录INFO级别日志"""
        extra = self._get_extra(kwargs)
        self._logger.bind(**extra).info(msg)
    
    def warning(self, msg, *args, **kwargs):
        """记录WARNING级别日志"""
        extra = self._get_extra(kwargs)
        self._logger.bind(**extra).warning(msg)
    
    def error(self, msg, *args, **kwargs):
        """记录ERROR级别日志"""
        extra = self._get_extra(kwargs)
        exc_info = kwargs.get('exc_info', False)
        self._logger.bind(**extra).error(msg, exception=exc_info)
    
    def critical(self, msg, *args, **kwargs):
        """记录CRITICAL级别日志"""
        extra = self._get_extra(kwargs)
        exc_info = kwargs.get('exc_info', False)
        self._logger.bind(**extra).critical(msg, exception=exc_info)
    
    def exception(self, msg, *args, **kwargs):
        """记录带有异常堆栈的ERROR级别日志"""
        extra = self._get_extra(kwargs)
        self._logger.bind(**extra).exception(msg)
    
    def _get_extra(self, kwargs):
        """从kwargs中提取extra信息"""
        extra = kwargs.get('extra', {})
        if 'request_id' not in extra:
            try:
                extra['request_id'] = request_ctx.get_trace_key()
            except Exception:
                extra['request_id'] = 'system'
        return extra


# 初始化logger并创建接口
_base_logger = setup_logger()
logger = LoggerInterface(_base_logger)

# 导出日志器
__all__ = ["logger"]

# 记录日志初始化完成
logger.info("Logger initialization completed with loguru")