# -*- coding: utf-8 -*-
"""
日志系统模块 (已修改，采用线程安全的异步DB Sink)

提供全局日志记录功能，使用loguru增强日志展示，支持请求上下文和链路追踪。
"""
import sys
import json
from datetime import datetime
import queue # 导入 queue
import asyncio # 导入 asyncio
import threading # 导入 threading 用于获取当前线程

from loguru import logger as loguru_logger
from colorama import init as colorama_init

# 假设这些导入路径正确
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.config import settings
# from bot_api_v1.app.services.log_service import LogService # 导入 LogService
from pathlib import Path
from dotenv import load_dotenv
import os

# 初始化colorama
colorama_init()

# 移除默认的loguru处理器
loguru_logger.remove()

# 加载环境变量
load_dotenv()




# --- 新增：检测是否在Celery环境中运行 ---
def is_running_in_celery():
    """检测当前代码是否在Celery工作进程中运行"""
    import sys
    return any('celery' in arg for arg in sys.argv)

# --- 新增：Celery环境下的日志处理器 ---
class CeleryLogHandler:
    """通过Celery任务处理日志持久化"""
    # 使用进程本地存储而不是类变量
    def __init__(cls):
        # 这些变量不会在类级别初始化，而是在每个进程中单独初始化
        pass
    @classmethod
    def _get_process_local_storage(cls):
        """获取进程本地存储"""
        if not hasattr(cls, '_process_local'):
            # 为每个进程创建独立的存储
            import multiprocessing
            cls._process_local = {
                'log_buffer': [],
                'buffer_size': 10,
                'buffer_lock': threading.Lock(),
                'flush_timer': None,
                'process_id': os.getpid(),  # 记录进程ID用于调试
                'last_flush_time': datetime.now()
            }
        return cls._process_local
    
    @classmethod
    def _flush_logs(cls):
        """将缓冲区中的日志发送到Celery任务队列"""
        storage = cls._get_process_local_storage()
        
        with storage['buffer_lock']:
            if not storage['log_buffer']:
                return
                
            logs_to_send = storage['log_buffer'].copy()
            storage['log_buffer'] = []
            storage['last_flush_time'] = datetime.now()
        
        try:
            # 导入并调用批量Celery任务
            from bot_api_v1.app.tasks.celery_tasks import save_logs_batch
            save_logs_batch.delay(logs_to_send)
            print(f"[{datetime.now()}] INFO: 进程 {storage['process_id']} 已发送 {len(logs_to_send)} 条日志到Celery批处理队列")
        except Exception as e:
            print(f"[{datetime.now()}] ERROR: 进程 {storage['process_id']} 发送日志到Celery批处理队列失败: {e}", file=sys.stderr)
            # 失败时回退到单条处理
            try:
                from bot_api_v1.app.tasks.celery_tasks import save_log_to_db
                for log_data in logs_to_send:
                    save_log_to_db.delay(**log_data)
            except Exception as fallback_err:
                print(f"[{datetime.now()}] ERROR: 进程 {storage['process_id']} 回退到单条处理也失败: {fallback_err}", file=sys.stderr)
    
    @classmethod
    def _schedule_flush(cls):
        """安排定时刷新"""
        storage = cls._get_process_local_storage()
        
        if storage['flush_timer'] is not None:
            try:
                storage['flush_timer'].cancel()
            except:
                pass  # 忽略可能的错误
            
        # 创建新的定时器
        storage['flush_timer'] = threading.Timer(5.0, cls._flush_logs)
        storage['flush_timer'].daemon = True
        storage['flush_timer'].start()
    
    @classmethod
    def write(cls, message):
        """将日志发送到Celery任务队列"""
        if message.record["extra"].get("log_to_db", False):
            # 提取所需信息
            log_data = {
                "trace_key": message.record["extra"].get("request_id", 'system'),
                "method_name": message.record["extra"].get("db_method_name", message.record["function"]),
                "source": message.record["extra"].get("source", 'unknown'),
                "app_id": message.record["extra"].get("app_id"),
                "user_uuid": message.record["extra"].get("user_id"),
                "user_nickname": message.record["extra"].get("user_name"),
                "entity_id": message.record["extra"].get("entity_id"),
                "type": message.record["extra"].get("db_type", message.record["level"].name.lower()),
                "tollgate": message.record["extra"].get("tollgate", '-'),
                "level": message.record["level"].name.lower(),
                "para": None,
                "header": None,
                "body": message.record["extra"].get("db_body", message.record["message"]),
                "description": message.record["extra"].get("db_description", message.record["extra"].get("root_trace_key")),
                "memo": message.record["extra"].get("db_memo", message.record["message"]),
                "ip_address": message.record["extra"].get("ip_address"),
                # 添加进程信息用于调试
                # "process_id": os.getpid(),
                # "timestamp": datetime.now().isoformat(),
            }
            
            # 对于严重错误，立即处理而不是批处理
            if message.record["level"].no >= 40:  # ERROR及以上级别
                try:
                    # 使用同步方法直接保存日志，而不是通过Celery任务
                    from bot_api_v1.app.services.log_service import LogService
                    result = LogService.save_log_sync(**log_data)
                    if result:
                        print(f"[{datetime.now()}] INFO: 进程 {os.getpid()} 严重错误日志已同步保存到数据库")
                    else:
                        print(f"[{datetime.now()}] ERROR: 进程 {os.getpid()} 同步保存严重错误日志失败")
                    return
                except Exception as e:
                    print(f"[{datetime.now()}] ERROR: 进程 {os.getpid()} 发送严重错误日志到Celery队列失败: {e}", file=sys.stderr)
                    
                    try:
                        from bot_api_v1.app.tasks.celery_tasks import save_log_to_db
                        save_log_to_db.delay(**log_data)
                        print(f"[{datetime.now()}] INFO: 进程 {os.getpid()} 严重错误日志已发送到Celery队列（回退）")
                    except Exception as fallback_err:
                        print(f"[{datetime.now()}] ERROR: 进程 {os.getpid()} 发送严重错误日志到Celery队列失败: {fallback_err}", file=sys.stderr)
            
            # 获取进程本地存储
            storage = cls._get_process_local_storage()
            
            # 检查上次刷新时间，如果超过10秒，强制刷新
            time_since_last_flush = (datetime.now() - storage['last_flush_time']).total_seconds()
            if time_since_last_flush > 10:
                cls._flush_logs()
                
            # 其他日志加入缓冲区
            with storage['buffer_lock']:
                storage['log_buffer'].append(log_data)
                buffer_size = len(storage['log_buffer'])
                
            # 如果缓冲区达到阈值，立即刷新
            if buffer_size >= storage['buffer_size']:
                cls._flush_logs()
            else:
                # 否则安排定时刷新
                cls._schedule_flush()




# --- 新增：线程安全的异步数据库日志 Sink ---
class AsyncDatabaseLogSink:
    def __init__(self):
        self.log_queue = queue.Queue() # 使用线程安全的队列
        self._consumer_task = None # 后台消费者任务
        self._loop = None # 事件循环
        self._stop_event = asyncio.Event() # 用于优雅停止的事件

    def write(self, message):
        """
        Loguru 调用此方法来写入日志记录 (可从任何线程调用).
        我们将日志记录放入队列。
        """
        # message 是 Loguru 的 Record 对象 (一个字典)
        # 我们只处理我们标记为需要存入数据库的日志
        if message.record["extra"].get("log_to_db", False):
            # 提取所需信息放入队列
            log_data = {
                "trace_key": message.record["extra"].get("request_id", 'system'),
                "method_name": message.record["extra"].get("db_method_name", message.record["function"]), # 优先使用 extra 中指定的
                "source": message.record["extra"].get("source", 'unknown'),
                "app_id": message.record["extra"].get("app_id"),
                "user_uuid": message.record["extra"].get("user_id"),
                "user_nickname": message.record["extra"].get("user_name"),
                "entity_id": message.record["extra"].get("entity_id"),
                "type": message.record["extra"].get("db_type", message.record["level"].name.lower()), # 优先使用 extra
                "tollgate": message.record["extra"].get("tollgate", '-'),
                "level": message.record["level"].name.lower(),
                "para": None, # 按需从 extra 获取或留空
                "header": None, # 按需从 extra 获取或留空
                "body": message.record["extra"].get("db_body", message.record["message"]), # 优先使用 extra
                "description": message.record["extra"].get("db_description", message.record["extra"].get("root_trace_key")),
                "memo": message.record["extra"].get("db_memo", message.record["message"]), # 优先使用 extra
                "ip_address": message.record["extra"].get("ip_address"),
                # "created_at": message.record["time"] # 使用 loguru 的时间
            }
            # 使用 put_nowait 避免阻塞日志发出线程，如果队列满了则日志会丢失 (需要监控)
            try:
                self.log_queue.put_nowait(log_data)
            except queue.Full:
                # 可以选择在这里记录一个本地错误日志，表明DB日志队列已满
                print(f"[{datetime.now()}] WARNING: Database log queue is full. Log message dropped.", file=sys.stderr)
            except Exception as e:
                 print(f"[{datetime.now()}] ERROR: Failed to put log in queue: {e}", file=sys.stderr)


    async def _consume(self):
        """异步消费者，从队列获取日志并保存到数据库"""
        from bot_api_v1.app.services.log_service import LogService

        print(f"[{datetime.now()}] INFO: Starting database log consumer task...")
        if not self._loop:
            print(f"[{datetime.now()}] ERROR: Event loop not set for DB log consumer.", file=sys.stderr)
            return

        while not self._stop_event.is_set():
            try:
                log_data = await self._loop.run_in_executor(None, lambda: self.log_queue.get(timeout=1))

                if log_data is None:
                    print(f"[{datetime.now()}] INFO: DB log consumer received stop signal.")
                    break

                try:
                    # 调用 LogService.save_log
                    await LogService.save_log(**log_data)
                except Exception as db_err:
                    # 这里记录错误到 stderr，避免循环依赖 logger
                    print(f"[{datetime.now()}] ERROR: Failed to save log to database via consumer: {db_err}\nData: {log_data}", file=sys.stderr)

                self.log_queue.task_done()

            except queue.Empty:
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                print(f"[{datetime.now()}] INFO: DB log consumer task cancelled.")
                break
            except Exception as e:
                print(f"[{datetime.now()}] CRITICAL: Database log consumer task encountered an error: {e}", file=sys.stderr)
                await asyncio.sleep(5)

        print(f"[{datetime.now()}] INFO: Database log consumer task finished.")


    def start(self, loop: asyncio.AbstractEventLoop):
        """启动后台消费者任务"""
        if self._consumer_task is None or self._consumer_task.done():
            self._loop = loop
            self._stop_event.clear()
            self._consumer_task = self._loop.create_task(self._consume())
            print(f"[{datetime.now()}] INFO: DB log consumer task scheduled.")
        else:
            print(f"[{datetime.now()}] WARNING: DB log consumer task already running.")

    async def stop(self):
        """优雅地停止后台消费者任务"""
        if self._consumer_task and not self._consumer_task.done():
            print(f"[{datetime.now()}] INFO: Attempting to stop DB log consumer task...")
            self._stop_event.set() # 设置停止事件
            # 可以选择向队列发送一个 None 作为停止信号
            try:
                self.log_queue.put_nowait(None)
            except queue.Full:
                print(f"[{datetime.now()}] WARNING: DB log queue full while trying to send stop signal.")

            try:
                # 等待任务结束，设置超时
                await asyncio.wait_for(self._consumer_task, timeout=10.0)
                print(f"[{datetime.now()}] INFO: DB log consumer task stopped gracefully.")
            except asyncio.TimeoutError:
                print(f"[{datetime.now()}] WARNING: DB log consumer task did not stop within timeout. Cancelling forcefully.")
                self._consumer_task.cancel()
            except Exception as e:
                 print(f"[{datetime.now()}] ERROR: Error while stopping DB log consumer: {e}")
        self._consumer_task = None
        self._loop = None
# --- End AsyncDatabaseLogSink ---


# 全局 Sink 实例 (稍后启动)
# 注意：在多进程环境（如 Gunicorn 使用多个 worker）中，这种全局实例需要更复杂的处理
# 对于单进程异步应用（如 uvicorn 单 worker），这是可行的
db_log_sink = AsyncDatabaseLogSink()


def setup_logger():
    """初始化并配置logger"""
    log_level = settings.LOG_LEVEL.upper()
    log_dir = Path(settings.LOG_FILE_PATH, Path(__file__).parent.parent / "logs")
    log_dir.mkdir(exist_ok=True)

    # 添加控制台输出处理器 (保持不变)
    loguru_logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<blue>{extra[tollgate]}</blue> | "
            "<blue>{extra[source]}</blue> | "
            "<cyan>{extra[app_id]}</cyan> | "
            "<magenta>{extra[user_id]}</magenta> | "
            "<yellow>{extra[user_name]}</yellow> | "
            "<bold><blue>[{extra[request_id]}]</blue></bold> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> | " # 注意：这里没有行号
            "<level>{message}</level>"
        ),
        level=log_level, colorize=True, backtrace=True, diagnose=True,
    )

    # 添加文件处理器 (保持不变)
    loguru_logger.add(
        log_dir / "api.log",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<blue>{extra[tollgate]}</blue> | "
            "<blue>{extra[source]}</blue> | "
            "<cyan>{extra[app_id]}</cyan> | "
            "<magenta>{extra[user_id]}</magenta> | "
            "<yellow>{extra[user_name]}</yellow> | "
            "<bold><blue>[{extra[request_id]}]</blue></bold> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> | " # 注意：这里没有行号
            "<level>{message}</level>"
        ),
        level=log_level, rotation="00:00", compression="gz", retention="30 days",
        encoding="utf-8", backtrace=True, diagnose=True,
    )

    # --- 修改：添加异步数据库 Sink ---
    # 过滤规则：只处理 level >= INFO 且 extra 中包含 'log_to_db' = True 的记录
    def db_filter(record):
        return record["extra"].get("log_to_db", False) and record["level"].no >= loguru_logger.level("INFO").no


    if is_running_in_celery():
        loguru_logger.add(
            CeleryLogHandler.write,
            level="INFO",
            filter=db_filter,
            enqueue=False
        )
    else:
        # 启动异步数据库 Sink
        loguru_logger.add(
            db_log_sink.write, # 将 sink 实例的 write 方法作为 sink
            level="INFO",      # 最低处理 INFO 级别
            filter=db_filter,  # 使用上面的过滤器
            enqueue=False      # Loguru 的 enqueue 对我们的自定义队列模式不是必需的
                            # 并且在异步 Sink 中使用 enqueue=True 可能导致问题
        )
    # --- 结束修改 ---

    # 初始绑定保持不变
    return loguru_logger.bind(request_id="-", source="-", app_id="-", user_id="-", user_name="-",tollgate="-")


class LoggerInterface:
    """日志接口封装"""

    def __init__(self, logger_instance):
        self._logger = logger_instance

    def _prepare_extra(self, kwargs):
        """准备 extra 字典，合并上下文信息"""
        extra = kwargs.pop('extra', {}) # 从 kwargs 中移除 extra
        # 获取最新的上下文数据
        current_ctx = request_ctx.get_context()
        # 更新 extra，优先使用 kwargs 中提供的值，其次是上下文，最后是默认值
        final_extra = {
            'request_id': current_ctx.get('trace_key', 'system'),
            'source': current_ctx.get('source', '-'),
            'app_id': current_ctx.get('app_id', '-'),
            'user_id': current_ctx.get('user_id', '-'),
            'user_name': current_ctx.get('user_name', '-'),
            'tollgate': f"{current_ctx.get('base_tollgate', '-')}-{current_ctx.get('current_tollgate', '-')}",
            'ip_address': current_ctx.get('ip_address'), # 从上下文获取IP
            **extra # 应用调用时传入的 extra 覆盖默认值
        }
        # 保留原始 kwargs 中的 exc_info 等参数
        final_kwargs = kwargs
        return final_extra, final_kwargs


    def debug(self, msg, *args, **kwargs):
        extra, remaining_kwargs = self._prepare_extra(kwargs)
        self._logger.bind(**extra).debug(msg, *args, **remaining_kwargs)

    def info(self, msg, *args, **kwargs):
        extra, remaining_kwargs = self._prepare_extra(kwargs)
        self._logger.bind(**extra).info(msg, *args, **remaining_kwargs)

    def warning(self, msg, *args, **kwargs):
        extra, remaining_kwargs = self._prepare_extra(kwargs)
        self._logger.bind(**extra).warning(msg, *args, **remaining_kwargs)

    def error(self, msg, *args, **kwargs):
        """记录ERROR级别日志，自动标记以便写入数据库"""
        extra, remaining_kwargs = self._prepare_extra(kwargs)
        exc_info = remaining_kwargs.get('exc_info', False) # 保留 exc_info 处理

        # --- 修改：标记此日志需要写入数据库 ---
        extra["log_to_db"] = True
        extra["db_level"] = "error" # 可选，明确指定DB中的级别
        # 如果需要，可以传递特定的 method_name 等给 DB Sink
        if 'method_name' in remaining_kwargs:
             extra['db_method_name'] = remaining_kwargs.pop('method_name')
        # 将详细错误（如果计算了）放入 extra 供 sink 使用
        error_detail, error_traceback = self._get_error_details(exc_info)
        if error_detail or error_traceback:
             full_error_info = f"{msg}\n\nDetails: {error_detail or 'No details'}"
             if error_traceback: full_error_info += f"\n\nTraceback:\n{error_traceback}"
             extra["db_body"] = full_error_info # 让 sink 处理 body
             extra["db_memo"] = msg # 保持 memo 简洁

        # --- 修改：不再调用 register_task ---
        # 只调用底层的 loguru logger
        self._logger.bind(**extra).error(msg, *args, **remaining_kwargs) # 传递原始 exc_info

    def critical(self, msg, *args, **kwargs):
        extra, remaining_kwargs = self._prepare_extra(kwargs)
        extra["log_to_db"] = True # Critical 错误也应该记录到DB
        extra["db_level"] = "critical"
        if 'method_name' in remaining_kwargs: extra['db_method_name'] = remaining_kwargs.pop('method_name')
        # ... (可以添加错误详情提取逻辑) ...
        self._logger.bind(**extra).critical(msg, *args, **remaining_kwargs)

    def exception(self, msg, *args, **kwargs):
        """记录带有异常堆栈的ERROR级别日志"""
        # exception() 相当于 error() 并自动设置了 exc_info=True
        kwargs['exc_info'] = True
        self.error(msg, *args, **kwargs) # 直接调用修改后的 error 方法

    def info_to_db(self, msg, *args, **kwargs):
        """记录 INFO 级别日志，并强制标记写入数据库"""
        extra, remaining_kwargs = self._prepare_extra(kwargs)

        # --- 修改：标记此日志需要写入数据库 ---
        extra["log_to_db"] = True
        extra["db_level"] = "info" # 指定DB中的级别
        # 传递 method_name 等信息给 Sink
        if 'method_name' in remaining_kwargs:
             extra['db_method_name'] = remaining_kwargs.pop('method_name')
        # 对于 info_to_db，通常 msg 就是主要内容
        extra["db_memo"] = msg
        # 如果需要区分 body 和 memo，可以设计 extra 字段
        # extra["db_body"] = ...

        # --- 修改：不再调用 register_task ---
        self._logger.bind(**extra).info(msg, *args, **remaining_kwargs)

    def _get_error_details(self, exc_info):
        """辅助方法：提取异常详情和堆栈"""
        error_detail = None
        error_traceback = None
        if exc_info:
            import traceback
            current_exc_info = sys.exc_info() # 获取当前线程的异常信息
            exc_type, exc_value, exc_tb = None, None, None

            if isinstance(exc_info, tuple) and len(exc_info) == 3:
                 exc_type, exc_value, exc_tb = exc_info # 如果传入了异常元组
            elif isinstance(exc_info, Exception):
                 exc_value = exc_info # 如果直接传入了异常对象
                 exc_type = type(exc_value)
                 exc_tb = exc_value.__traceback__
            elif exc_info is True and current_exc_info[1] is not None:
                 exc_type, exc_value, exc_tb = current_exc_info # 使用当前上下文的异常

            if exc_value is not None:
                 error_detail = str(exc_value)
                 try:
                      # 尝试格式化堆栈跟踪
                      error_traceback = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
                 except Exception:
                      error_traceback = "Failed to format traceback." # 格式化失败时提供提示

        return error_detail, error_traceback


# --- 修改：初始化和导出 ---
# 初始化logger（但不启动DB Sink的消费者）
_base_logger = setup_logger()
logger = LoggerInterface(_base_logger)

# 导出日志器和 Sink 实例（应用启动时需要启动 Sink）
__all__ = ["logger", "db_log_sink"]

# 记录日志初始化完成
logger.info("Logger initialization completed with loguru and async DB sink configured (consumer task needs starting).")

# --- 如何启动和停止消费者任务？---
# 你需要在你的主应用（例如 FastAPI/Starlette 应用）的启动和关闭事件中处理
# 示例 (FastAPI):
#
# from fastapi import FastAPI
# from your_logger_module import logger, db_log_sink
# import asyncio
#
# app = FastAPI()
#
# @app.on_event("startup")
# async def startup_event():
#     logger.info("Application startup: Starting DB log consumer...")
#     try:
#         loop = asyncio.get_running_loop()
#         db_log_sink.start(loop) # 启动消费者
#     except Exception as e:
#         logger.error(f"Failed to start DB log consumer: {e}", exc_info=True)
#
# @app.on_event("shutdown")
# async def shutdown_event():
#     logger.info("Application shutdown: Stopping DB log consumer...")
#     try:
#         await db_log_sink.stop() # 优雅停止
#     except Exception as e:
#         logger.error(f"Failed to stop DB log consumer gracefully: {e}", exc_info=True)
#
# # ... 你的其他 API 路由 ...