# # core/logger.py
# import logging
# from typing import Optional, Dict, Any
# from contextvars import ContextVar
# import functools
# import contextlib

# from bot_api_v1.app.core.context import request_ctx

# # Create the logger first
# original_logger = logging.getLogger(__name__)  # Use the module's logger as the original logger

# # Create a log context variable
# _log_context_var: ContextVar[Dict[str, Any]] = ContextVar('log_context', default={})

# class EnhancedLogger:
#     """增强的日志器，支持上下文和数据库日志"""
    
#     def __init__(self, base_logger):
#         self._logger = base_logger
    
#     def _log(self, level, msg, *args, **kwargs):
#         """通用日志方法"""
#         # 获取上下文中的trace_key
#         if 'extra' not in kwargs:
#             kwargs['extra'] = {}
            
#         if 'request_id' not in kwargs['extra']:
#             try:
#                 kwargs['extra']['request_id'] = request_ctx.get_trace_key()
#             except Exception:
#                 kwargs['extra']['request_id'] = 'system'
        
#         # 调用基础日志器记录文本日志
#         log_method = getattr(self._logger, level)
#         log_method(msg, *args, **kwargs)
        
#         # 检查是否需要同时记录到数据库
#         context = _log_context_var.get()
#         if context.get('db_log_enabled', False):
#             self._log_to_database(level, msg, context, kwargs.get('extra', {}))
    
#     def _log_to_database(self, level, msg, context, extra):
#         """记录日志到数据库"""
#         try:
#             from bot_api_v1.app.services.log_service import LogService
#             import asyncio
            
#             # 从上下文获取必要信息
#             trace_key = extra.get('request_id') or context.get('trace_key') or request_ctx.get_trace_key()
#             method_name = context.get('method_name', 'unknown')
            
#             # 创建异步任务记录日志
#             log_task = asyncio.create_task(
#                 LogService.save_log(
#                     trace_key=trace_key,
#                     method_name=method_name,
#                     source=context.get('source', 'api'),
#                     type=context.get('type', 'service'),
#                     tollgate=context.get('tollgate', '20-1'),
#                     level=level,
#                     body=msg,
#                     memo=msg,
#                 )
#             )
            
#             # 可选：注册任务到任务追踪器
#             try:
#                 from bot_api_v1.app.middlewares.logging_middleware import register_task
#                 register_task(log_task)
#             except ImportError:
#                 pass
                
#         except Exception as e:
#             # 记录日志到数据库失败，使用文本日志记录错误
#             self._logger.error(f"记录日志到数据库失败: {str(e)}")
    
#     def debug(self, msg, *args, **kwargs):
#         self._log('debug', msg, *args, **kwargs)
    
#     def info(self, msg, *args, **kwargs):
#         self._log('info', msg, *args, **kwargs)
    
#     def warning(self, msg, *args, **kwargs):
#         self._log('warning', msg, *args, **kwargs)
    
#     def error(self, msg, *args, **kwargs):
#         self._log('error', msg, *args, **kwargs)
    
#     def critical(self, msg, *args, **kwargs):
#         self._log('critical', msg, *args, **kwargs)
    
#     def exception(self, msg, *args, **kwargs):
#         if 'exc_info' not in kwargs:
#             kwargs['exc_info'] = True
#         self._log('error', msg, *args, **kwargs)

#     @classmethod
#     def enable_db_logging(cls, **context_info):
#         """启用数据库日志记录"""
#         context = _log_context_var.get().copy()
#         context['db_log_enabled'] = True
#         context.update(context_info)
#         _log_context_var.set(context)
#         return context
    
#     @classmethod
#     def disable_db_logging(cls):
#         """禁用数据库日志记录"""
#         context = _log_context_var.get().copy()
#         context['db_log_enabled'] = False
#         _log_context_var.set(context)
#         return context

#     @classmethod
#     @contextlib.contextmanager
#     def db_logging_context(cls, **context_info):
#         """数据库日志上下文管理器"""
#         previous = _log_context_var.get().copy()
#         cls.enable_db_logging(**context_info)
#         try:
#             yield
#         finally:
#             _log_context_var.set(previous)

# # 创建增强的logger实例
# logger = EnhancedLogger(original_logger)

# # 导出增强的logger替代原始logger
# __all__ = ['logger']




import os
import logging
import json
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
import gzip
import shutil
from dotenv import load_dotenv

load_dotenv()

# 自定义GZip压缩旋转器
class GZipRotator:
    def __call__(self, source, dest):
        with open(source, 'rb') as f_in:
            with gzip.open(f"{dest}.gz", 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)  # 删除未压缩的原始文件

class RequestFormatter(logging.Formatter):
    def format(self, record):
        # 设置缺省值
        if not hasattr(record, 'request_id'):
            record.request_id = 'system'
        
        # 处理 headers        
        if hasattr(record, 'headers'):
            # 尝试将 headers 序列化为 JSON
            try:
                if isinstance(record.headers, dict):
                    record.headers = json.dumps(record.headers, ensure_ascii=False)
                elif isinstance(record.headers, str):
                    # 如果已经是字符串，检查是否是有效的 JSON
                    try:
                        json.loads(record.headers)
                    except:
                        record.headers = '{"error": "Invalid JSON string"}'
                else:
                    record.headers = '{"error": "Headers is neither dict nor string"}'
            except:
                record.headers = '{"error": "Serialization failed"}'
        else:
            record.headers = '{}'
            
        # 添加格式化内容并添加两个空行
        return super().format(record) + "\n\n"

def setup_logger(name: str = "api"):
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # 防止重复日志
    if logger.handlers:
        return logger

    if "LOG_LEVEL" not in os.environ:
        print("LOG_LEVEL not set, using default 'INFO'")

    formatter = RequestFormatter(
        '[%(asctime)s] [%(request_id)s] %(levelname)s in %(module)s: %(message)s | HEADERS=%(headers)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 设置日志目录
    LOG_DIR = Path(os.getenv("LOG_DIR", Path(__file__).parent.parent / "logs"))
    try:
        LOG_DIR.mkdir(exist_ok=True)
    except Exception as e:
        print(f"Failed to create log directory: {e}")
        raise

    # 基于时间的文件处理器，每天午夜轮转
    file_handler = TimedRotatingFileHandler(
        filename=LOG_DIR / "api.log",
        when='midnight',        # 每天午夜创建新文件
        interval=1,             # 时间间隔为1天
        backupCount=30,         # 保留30天的日志
        encoding="utf-8",
        utc=True                # 使用UTC时间，避免时区问题
    )
    
    # 设置文件名后缀格式为日期
    file_handler.suffix = "%Y-%m-%d"
    file_handler.extMatch = r"^\d{4}-\d{2}-\d{2}$"
    file_handler.setFormatter(formatter)
    
    # 使用GZip压缩旋转器，节省空间
    file_handler.rotator = GZipRotator()
    
    # 添加处理器
    logger.addHandler(file_handler)
    
    # 生产环境通常不需要控制台输出，但可以根据环境变量决定
    if os.getenv("ENVIRONMENT", "production").lower() != "production":
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    logger.info("Logger initialization completed", extra={"request_id": "system"})
    return logger

# 延迟初始化
logger = setup_logger()
