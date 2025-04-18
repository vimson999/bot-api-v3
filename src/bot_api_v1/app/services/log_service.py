import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import json
import sys

from sqlalchemy.ext.asyncio import AsyncSession
from bot_api_v1.app.models.log_trace import LogTrace
from bot_api_v1.app.db.session import async_session_maker,get_sync_db
import contextlib

class LogService:
    @staticmethod
    async def save_log(
        trace_key: str,
        method_name: str,
        source: str = "api",
        app_id: Optional[str] = None,
        user_uuid: Optional[str] = None,
        user_nickname: Optional[str] = None,
        entity_id: Optional[str] = None,
        type: str = "default",
        tollgate: str = "1-1",
        level: str = "info",
        para: Optional[Dict[str, Any]] = None,
        header: Optional[Dict[str, Any]] = None,
        body: Optional[Any] = None,
        description: Optional[str] = None,  # 添加description参数
        memo: Optional[str] = None,
        ip_address: Optional[str] = None
    ):
        from bot_api_v1.app.core.logger import logger
        session: Optional[AsyncSession] = None # 显式初始化

        """异步保存日志到PostgreSQL数据库"""
        async with contextlib.AsyncExitStack() as stack:
            try:
                # 确保获取新的会话
                session = await stack.enter_async_context(async_session_maker())
                
                # 处理para参数，去除不可序列化对象
                processed_para = None
                if para is not None:
                    processed_para = {}
                    for key, value in para.items():
                        # 跳过不可序列化的对象
                        if isinstance(value, AsyncSession) or hasattr(value, '__dict__') and not hasattr(value, 'to_dict'):
                            continue
                        processed_para[key] = value
                
                # 处理header参数，去除不可序列化对象
                processed_header = None
                if header is not None:
                    processed_header = {}
                    for key, value in header.items():
                        # 跳过不可序列化的对象
                        if isinstance(value, AsyncSession) or hasattr(value, '__dict__') and not hasattr(value, 'to_dict'):
                            continue
                        processed_header[key] = value
                
                # 处理body
                processed_body = None
                if body is not None:
                    if isinstance(body, dict) or isinstance(body, list):
                        processed_body = json.dumps(body)
                    elif isinstance(body, str):
                        processed_body = body
                    else:
                        processed_body = str(body)
                
                # 创建日志条目
                log_entry = LogTrace(
                    trace_key=trace_key,
                    source=source,
                    app_id=app_id,
                    user_uuid=user_uuid,
                    user_nickname=user_nickname,
                    entity_id=entity_id,
                    type=type,
                    method_name=method_name,
                    tollgate=tollgate,
                    level=level,
                    para=processed_para,
                    header=processed_header,
                    body=processed_body[:10000] if processed_body else None,
                    description=description[:10000] if description else None,  # 添加description字段
                    memo=memo,
                    ip_address=ip_address,
                    created_at=datetime.now()
                )
                
                session.add(log_entry)
                await session.commit()
                # return True
            except Exception as e:
                # >>> 在这里使用导入的 logger <<<
                # 注意：如果这里的 logger.error 再次触发异步DB日志，仍可能出问题
                # 更安全的做法是直接打印到 stderr 或记录到文件日志
                error_msg = f"Failed to save log to PostgreSQL database: {str(e)}"
                print(f"[{datetime.now()}] {error_msg}", file=sys.stderr) # 直接打印错误
                # 或者如果你确信 logger.error 配置了安全的同步处理器:
                # logger.error(error_msg, exc_info=True, extra={'request_id': trace_key}) # 但要小心循环！

                if session is not None: # 检查 session 是否已成功创建
                    try:
                        await session.rollback()
                    except Exception as rb_err:
                         print(f"[{datetime.now()}] ERROR: Failed to rollback session after DB log error: {rb_err}", file=sys.stderr)
                # 注意：保存失败时不再返回 False

    # --- 新增：同步保存日志方法 ---
    @staticmethod
    def save_log_sync(
        trace_key: str,
        method_name: str,
        source: str = "api",
        app_id: Optional[str] = None,
        user_uuid: Optional[str] = None,
        user_nickname: Optional[str] = None,
        entity_id: Optional[str] = None,
        type: str = "default",
        tollgate: str = "1-1",
        level: str = "info",
        para: Optional[Dict[str, Any]] = None,
        header: Optional[Dict[str, Any]] = None,
        body: Optional[Any] = None,
        description: Optional[str] = None,
        memo: Optional[str] = None,
        ip_address: Optional[str] = None
    ):
        """同步保存日志到PostgreSQL数据库，适用于Celery等非异步环境"""
        try:
            # 使用同步数据库会话
            with get_sync_db() as session:
                # 处理para参数，去除不可序列化对象
                processed_para = None
                if para is not None:
                    processed_para = {}
                    for key, value in para.items():
                        # 跳过不可序列化的对象
                        if hasattr(value, '__dict__') and not hasattr(value, 'to_dict'):
                            continue
                        processed_para[key] = value
                
                # 处理header参数，去除不可序列化对象
                processed_header = None
                if header is not None:
                    processed_header = {}
                    for key, value in header.items():
                        # 跳过不可序列化的对象
                        if hasattr(value, '__dict__') and not hasattr(value, 'to_dict'):
                            continue
                        processed_header[key] = value
                
                # 处理body
                processed_body = None
                if body is not None:
                    if isinstance(body, dict) or isinstance(body, list):
                        processed_body = json.dumps(body)
                    elif isinstance(body, str):
                        processed_body = body
                    else:
                        processed_body = str(body)
                
                # 创建日志条目
                log_entry = LogTrace(
                    trace_key=trace_key,
                    source=source,
                    app_id=app_id,
                    user_uuid=user_uuid,
                    user_nickname=user_nickname,
                    entity_id=entity_id,
                    type=type,
                    method_name=method_name,
                    tollgate=tollgate,
                    level=level,
                    para=processed_para,
                    header=processed_header,
                    body=processed_body[:10000] if processed_body else None,
                    description=description[:10000] if description else None,
                    memo=memo,
                    ip_address=ip_address,
                    created_at=datetime.now()
                )
                
                session.add(log_entry)
                session.commit()
                return True
                
        except Exception as e:
            error_msg = f"Failed to save log to PostgreSQL database (sync): {str(e)}"
            print(f"[{datetime.now()}] {error_msg}", file=sys.stderr)
            return False
    
    # --- 新增：使用事件循环运行异步方法的同步包装器 ---
    @staticmethod
    def save_log_sync_wrapper(
        trace_key: str,
        method_name: str,
        source: str = "api",
        app_id: Optional[str] = None,
        user_uuid: Optional[str] = None,
        user_nickname: Optional[str] = None,
        entity_id: Optional[str] = None,
        type: str = "default",
        tollgate: str = "1-1",
        level: str = "info",
        para: Optional[Dict[str, Any]] = None,
        header: Optional[Dict[str, Any]] = None,
        body: Optional[Any] = None,
        description: Optional[str] = None,
        memo: Optional[str] = None,
        ip_address: Optional[str] = None
    ):
        """
        同步包装器，通过创建新的事件循环来运行异步save_log方法
        适用于需要在同步上下文中调用异步方法的场景
        """
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                # 运行异步方法直到完成
                return loop.run_until_complete(
                    LogService.save_log(
                        trace_key=trace_key,
                        method_name=method_name,
                        source=source,
                        app_id=app_id,
                        user_uuid=user_uuid,
                        user_nickname=user_nickname,
                        entity_id=entity_id,
                        type=type,
                        tollgate=tollgate,
                        level=level,
                        para=para,
                        header=header,
                        body=body,
                        description=description,
                        memo=memo,
                        ip_address=ip_address
                    )
                )
            finally:
                loop.close()
        except Exception as e:
            error_msg = f"Failed to save log using sync wrapper: {str(e)}"
            print(f"[{datetime.now()}] {error_msg}", file=sys.stderr)
            return False