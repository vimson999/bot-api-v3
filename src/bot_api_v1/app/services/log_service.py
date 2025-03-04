
# bot_api_v1/app/services/log_service.py
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
        user_id: Optional[str] = None,
        uni_id: Optional[str] = None,
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
                
                # PostgreSQL可以直接存储JSON，不需要序列化
                processed_body = None
                if body is not None:
                    if isinstance(body, dict) or isinstance(body, list):
                        processed_body = json.dumps(body)  # 字典和列表转为JSON字符串
                    elif isinstance(body, str):
                        processed_body = body
                    else:
                        processed_body = str(body)
                
                # 创建日志条目
                log_entry = LogTrace(
                    trace_key=trace_key,
                    source=source,
                    app_id=app_id,
                    user_id=user_id,
                    uni_id=uni_id,
                    entity_id=entity_id,
                    type=type,
                    method_name=method_name,
                    tollgate=tollgate,
                    level=level,
                    para=para,  # PostgreSQL的JSONB类型可以直接存储字典
                    header=header,  # PostgreSQL的JSONB类型可以直接存储字典
                    body=processed_body[:10000] if processed_body else None,  # 限制大小
                    memo=memo,
                    ip_address=ip_address,
                    created_at=datetime.now()
                )
                
                session.add(log_entry)
                await session.commit()
                return True
            except Exception as e:
                # 使用正确的日志器记录错误
                logger.error(f"Failed to save log to PostgreSQL database: {str(e)}", exc_info=True)
                # 尝试回滚
                if 'session' in locals():
                    await session.rollback()
                return False


