"""
日志系统模块

提供全局日志记录功能，使用loguru增强日志展示，支持请求上下文和链路追踪。
"""
import sys
import json
from datetime import datetime

from loguru import logger as loguru_logger
from colorama import init as colorama_init

from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.config import settings
from pathlib import Path
from dotenv import load_dotenv
import os

# 初始化colorama，确保在Windows平台上也能正确显示颜色
colorama_init()

# 移除默认的loguru处理器
loguru_logger.remove()

# 加载环境变量
load_dotenv()

def setup_logger():
    """初始化并配置logger"""
    # 获取环境变量
    log_level = settings.LOG_LEVEL.upper()
    environment = settings.ENVIRONMENT.lower()
    
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
        # 日志格式应该使用与上下文相同的变量名
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<blue>{extra[tollgate]}</blue> | "
            "<blue>{extra[source]}</blue> | "
            "<cyan>{extra[app_id]}</cyan> | "
            "<magenta>{extra[user_id]}</magenta> | "
            "<yellow>{extra[user_name]}</yellow> | "
            "<bold><blue>[{extra[request_id]}]</blue></bold> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
            "<level>{message}</level>"
        ),
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )
    
    # 添加文件处理器
    loguru_logger.add(
        log_dir / "api.log",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{extra[tollgate]} | "
            "{extra[source]} | "
            "{extra[app_id]} | "
            "{extra[user_id]} | "
            "{extra[user_name]} | "
            "[{extra[request_id]}] | "
            "{level: <8} | "
            "{name}:{function} | "
            "{message}"
        ),        
        level=log_level,
        rotation="00:00",  # 每天午夜轮转
        compression="gz",  # 使用gzip压缩
        retention="30 days",  # 保留30天
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )
    
    return loguru_logger.bind(request_id="-", source="-", app_id="-", user_id="-", user_name="-",tollgate="-")


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
        """记录ERROR级别日志，同时保存到数据库"""
        # 1. 获取上下文信息
        extra = self._get_extra(kwargs)
        trace_key = extra.get('request_id', 'system')
        exc_info = kwargs.get('exc_info', False)
        
        # 2. 记录到文本日志
        self._logger.bind(**extra).error(msg, exception=exc_info)
        
        # 3. 获取其他日志相关信息
        method_name = kwargs.get('method_name', extra.get('method_name', 'unknown'))
        source = extra.get('source', 'api')
        app_id = extra.get('app_id', None)
        user_uuid = extra.get('user_id', None)
        user_nickname = extra.get('user_name', None)
        ip_address = extra.get('ip_address', None)
        
        # 确定tollgate值，错误通常使用base-9格式
        base_tollgate = extra.get('base_tollgate', '10')
        error_tollgate = f'{base_tollgate}-9'
        
        # 4. 使用全局任务系统注册异步日志任务，但不等待完成
        from bot_api_v1.app.tasks.base import register_task, TASK_TYPE_LOG
        from bot_api_v1.app.services.log_service import LogService
        
        try:
            # 如果提供了异常信息，获取更详细的错误内容
            error_detail = None
            error_traceback = None

            if exc_info:
                import traceback
                
                if isinstance(exc_info, Exception):
                    # 如果直接传入了异常对象
                    error_detail = str(exc_info)
                    # 获取这个异常的堆栈跟踪
                    error_traceback = ''.join(traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__))
                elif exc_info is True:
                    # 如果exc_info为True，获取当前异常信息
                    exc_type, exc_value, exc_tb = sys.exc_info()
                    if exc_value is not None:
                        error_detail = str(exc_value)
                        # 获取当前异常的堆栈跟踪
                        error_traceback = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))

            # 组合详细错误信息和堆栈跟踪
            full_error_info = f"{msg}\n\nDetails: {error_detail or 'No additional details'}"
            if error_traceback:
                full_error_info += f"\n\nTraceback:\n{error_traceback}"
            
            # 注册异步任务保存日志到数据库
            register_task(
                name=f"error_log:{method_name}",
                coro=LogService.save_log(
                    trace_key=trace_key,
                    method_name=method_name,
                    source=source,
                    app_id=app_id,
                    user_uuid=user_uuid,
                    user_nickname=user_nickname,
                    entity_id=None,
                    type="error",
                    tollgate=error_tollgate,
                    level="error",
                    para=None,
                    header=None,
                    body=full_error_info,  # 使用包含详细信息和堆栈跟踪的完整错误信息
                    memo=f"Error: {msg}",  # memo仍保持简短以便于快速概览
                    ip_address=ip_address
                ),
                timeout=60,  # 设置日志超时时间为60秒
                task_type=TASK_TYPE_LOG
            )
        except Exception as log_error:
            # 如果注册任务失败，记录到文本日志但不抛出异常
            self._logger.bind(**extra).warning(
                f"Error logging to database failed: {str(log_error)}"
            )

    
    def critical(self, msg, *args, **kwargs):
        """记录CRITICAL级别日志"""
        extra = self._get_extra(kwargs)
        exc_info = kwargs.get('exc_info', False)
        self._logger.bind(**extra).critical(msg, exception=exc_info)
    
    def exception(self, msg, *args, **kwargs):
        """记录带有异常堆栈的ERROR级别日志"""
        extra = self._get_extra(kwargs)
        self._logger.bind(**extra).exception(msg)
    
    
    # def gigg(self, level, msg, *args, **kwargs):
    #     """记录自定义级别日志"""
    #     extra = self._get_extra(kwargs)

    #     current_ctx = request_ctx.get_context()

    #     base_tollgate = current_ctx.get('base_tollgate', '-')
    #     current_tollgate = current_ctx.get('current_tollgate', '-')
    #     extra['tollgate'] = f'{base_tollgate}-{current_tollgate}'

    #     self._logger.bind(**extra).info(msg)

    def _get_extra(self, kwargs):
        """从kwargs中提取extra信息并增加请求上下文信息"""
        extra = kwargs.get('extra', {})
        # extra = copy.deepcopy(kwargs.get('extra', {}))  # 深度拷贝避免引用污染
        # current_ctx = copy.deepcopy(request_ctx.get_context())  # 深度拷贝上下文

        
        # 获取最新的上下文数据
        current_ctx = request_ctx.get_context()
        
        # 如果没有提供extra中的字段，则从请求上下文中获取
        if 'request_id' not in extra:
            extra['request_id'] = current_ctx.get('trace_key', 'system')
        
        # 添加其他上下文信息
        if 'source' not in extra:
            extra['source'] = current_ctx.get('source', '-')
        
        if 'app_id' not in extra:
            extra['app_id'] = current_ctx.get('app_id', '-')
        
        if 'user_id' not in extra:
            extra['user_id'] = current_ctx.get('user_id', '-')
        
        if 'user_name' not in extra:
            extra['user_name'] = current_ctx.get('user_name', '-')

        # 直接从上下文获取最新的tollgate值
        if 'tollgate' not in extra:
            base_tollgate = current_ctx.get('base_tollgate', '-')
            current_tollgate = current_ctx.get('current_tollgate', '-')
            extra['tollgate'] = f'{base_tollgate}-{current_tollgate}'
        
        return extra

    def info_to_db(self, msg, *args, **kwargs):
        """记录ERROR级别日志，同时保存到数据库"""
        # 1. 获取上下文信息
        extra = self._get_extra(kwargs)
        trace_key = extra.get('request_id', 'system')
        exc_info = kwargs.get('exc_info', False)
        
        # 2. 记录到文本日志
        self._logger.bind(**extra).info(msg)
        
        # 3. 获取其他日志相关信息
        method_name = kwargs.get('method_name', extra.get('method_name', 'unknown'))
        source = extra.get('source', 'api')
        app_id = extra.get('app_id', None)
        user_uuid = extra.get('user_id', None)
        user_nickname = extra.get('user_name', None)
        ip_address = extra.get('ip_address', None)
        
        # 确定tollgate值，错误通常使用base-9格式
        current_tollgate = extra.get('current_tollgate', '10')
        type = extra.get('type', 'api')


        # 4. 使用全局任务系统注册异步日志任务，但不等待完成
        from bot_api_v1.app.tasks.base import register_task, TASK_TYPE_LOG
        from bot_api_v1.app.services.log_service import LogService
        
        try:# 注册异步任务保存日志到数据库
            register_task(
                name=f"log_to_db:{method_name}",
                coro=LogService.save_log(
                    trace_key=trace_key,
                    method_name=method_name,
                    source=source,
                    app_id=app_id,
                    user_uuid=user_uuid,
                    user_nickname=user_nickname,
                    entity_id=None,
                    type=type,
                    tollgate=current_tollgate,
                    level="info",
                    para=None,
                    header=None,
                    body='',  # 使用包含详细信息和堆栈跟踪的完整错误信息
                    memo=msg,  # memo仍保持简短以便于快速概览
                    ip_address=ip_address
                ),
                timeout=60,  # 设置日志超时时间为60秒
                task_type=TASK_TYPE_LOG
            )
        except Exception as log_error:
            # 如果注册任务失败，记录到文本日志但不抛出异常
            self._logger.bind(**extra).warning(
                f"Error logging to database failed: {str(log_error)}"
            )



# 初始化logger并创建接口
_base_logger = setup_logger()
logger = LoggerInterface(_base_logger)

# 导出日志器
__all__ = ["logger"]

# 记录日志初始化完成
logger.info("Logger initialization completed with loguru")