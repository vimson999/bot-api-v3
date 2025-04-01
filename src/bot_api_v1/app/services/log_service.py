import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import json
from sqlalchemy.ext.asyncio import AsyncSession
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.models.log_trace import LogTrace
from bot_api_v1.app.db.session import async_session_maker
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
        memo: Optional[str] = None,
        ip_address: Optional[str] = None
    ):
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
                    para=processed_para,  # 使用处理后的para
                    header=processed_header,  # 使用处理后的header
                    body=processed_body[:10000] if processed_body else None,
                    memo=memo,
                    ip_address=ip_address,
                    created_at=datetime.now()
                )
                
                session.add(log_entry)
                await session.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to save log to PostgreSQL database: {str(e)}", exc_info=True)
                if 'session' in locals():
                    await session.rollback()
                return False