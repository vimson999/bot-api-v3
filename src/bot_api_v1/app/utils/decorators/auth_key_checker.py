import uuid
import json
from functools import wraps
from typing import Optional, Dict, Any, Callable

from fastapi import Header, HTTPException, Depends, Request, status
from sqlalchemy import select, update, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from bot_api_v1.app.models.meta_auth_key import MetaAuthKey
from bot_api_v1.app.db.session import get_db, async_session_maker
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx


def require_auth_key(exempt: bool = False):
    """
    API授权密钥验证装饰器
    
    Args:
        exempt: 是否豁免验证，设为True时跳过验证但仍记录访问
    
    用法:
        @router.post("/api/endpoint")
        @require_auth_key()
        async def endpoint(request: Request):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = None
            db = None
            need_close = False
            key_obj = None  # 在函数开始时初始化
            trace_key = request_ctx.get_trace_key()


            # 步骤1：获取请求对象
            request = _extract_request_object(args, kwargs)
            if not request:
                logger.error("验证授权密钥：无法获取请求对象")
                if not exempt:
                    raise HTTPException(status_code=400, detail="无法验证请求")
                return await func(*args, **kwargs)
            
            # 步骤2：从请求头获取授权密钥
            auth_key = _get_auth_key_from_headers(request)
            
            # 步骤3：处理缺少密钥的情况
            if not auth_key:
                return await _handle_missing_key(func, args, kwargs, exempt)
            
            # 步骤4：获取数据库会话
            db, need_close = await _get_database_session(kwargs, exempt)
            if not db and exempt:
                return await func(*args, **kwargs)
            
            try:
                # 步骤5：验证密钥
                key_obj = await _validate_key(db, auth_key, exempt)
                if not key_obj:
                    if exempt:
                        return await func(*args, **kwargs)
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="无效的授权密钥"
                    )
                
                # 步骤6：检查密钥状态
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                
                # 检查过期状态
                if await _check_key_expired(db, request, key_obj, now, exempt):
                    return await func(*args, **kwargs) if exempt else None
                
                # 检查调用次数限制
                if await _check_call_limit_exceeded(db, request, key_obj, now, exempt):
                    return await func(*args, **kwargs) if exempt else None
                
                # 步骤7：执行原始函数
                result = await func(*args, **kwargs)
                
                # 步骤8：检查调用是否成功
                is_successful = _check_api_call_success(result)
                
                # 步骤9：只有在成功时才更新调用次数
                if is_successful and db and key_obj:
                    await _update_call_count(db, key_obj)
                    logger.info(f"API调用成功，扣除调用次数: {key_obj.key_value}")
                elif not is_successful:
                    logger.info(f"API调用返回业务失败，不扣除调用次数: {key_obj.key_value if key_obj else 'unknown'}")
                
                # 返回原始函数的结果
                return result
            except Exception as e:
                # 函数执行失败，记录错误但不扣除调用次数
                logger.error(f"API执行异常，不扣除调用次数: {str(e)}", exc_info=True)
                raise
            finally:
                # 无论成功失败，都存储认证信息和清理资源
                if request and key_obj:
                    _store_auth_info(request, key_obj)
                
                if need_close and db:
                    await db.close()
            
        return wrapper
    
    return decorator


# 辅助函数

def _extract_request_object(args, kwargs) -> Optional[Request]:
    """从函数参数中提取Request对象"""
    # 检查位置参数
    for arg in args:
        if isinstance(arg, Request):
            return arg
    
    # 检查关键字参数
    for value in kwargs.values():
        if isinstance(value, Request):
            return value
    
    return None


def _get_auth_key_from_headers(request: Request) -> Optional[str]:
    """从请求头中获取授权密钥，支持多种常见格式"""
    auth_key = request.headers.get("Authorization") or request.headers.get("X-Auth-Key")
    
    if not auth_key:
        return None
        
    # 处理Bearer认证格式
    if auth_key.startswith("Bearer "):
        auth_key = auth_key[7:].strip()
    
    return auth_key


async def _handle_missing_key(func, args, kwargs, exempt: bool):
    """处理缺少授权密钥的情况"""
    if exempt:
        logger.debug("豁免验证模式：无授权密钥")
        return await func(*args, **kwargs)
    else:
        logger.warning("验证失败：缺少授权密钥")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少授权密钥"
        )


async def _get_database_session(kwargs, exempt: bool) -> tuple[Optional[AsyncSession], bool]:
    """获取数据库会话，如果没有现成的则创建一个"""
    db = kwargs.get("db")
    need_close = False
    
    if not db:
        try:
            db = async_session_maker()
            need_close = True
        except Exception as e:
            logger.error(f"创建数据库会话失败: {str(e)}", exc_info=True)
            if not exempt:
                raise HTTPException(status_code=500, detail="服务器内部错误")
            return None, False
    
    return db, need_close


async def _validate_key(db: AsyncSession, auth_key: str, exempt: bool) -> Optional[MetaAuthKey]:
    """验证授权密钥是否存在且有效"""
    try:
        stmt = select(MetaAuthKey).where(
            and_(
                MetaAuthKey.key_value == auth_key,
                MetaAuthKey.key_status == 1,
                MetaAuthKey.status == 1
            )
        )
        
        result = await db.execute(stmt)
        key_obj = result.scalar_one_or_none()
        
        if not key_obj:
            logger.warning(f"无效的授权密钥: {auth_key}")
        
        return key_obj
    except Exception as e:
        logger.error(f"验证密钥时数据库错误: {str(e)}", exc_info=True)
        if not exempt:
            raise HTTPException(status_code=500, detail="验证密钥时发生错误")
        return None


async def _check_key_expired(db: AsyncSession, request: Request, key_obj: MetaAuthKey, 
                            now: datetime, exempt: bool) -> bool:
    
    """检查密钥是否已过期，如果已过期则更新状态"""
    if not key_obj.expired_at or now <= key_obj.expired_at:
        return False
    
    # 密钥已过期，构建详细信息
    context = _get_request_context(request, now)
    
    update_note = (
        f"系统自动更新: 密钥已过期。时间: {context['time_str']}, "
        f"请求ID: {context['trace_id']}, 路径: {context['method']} {context['path']}, "
        f"IP: {context['client_ip']}"
    )
    
    # 更新密钥状态为已过期并记录详细信息
    try:
        await db.execute(
            update(MetaAuthKey)
            .where(MetaAuthKey.id == key_obj.id)
            .values(
                key_status=3,  # 3=已过期
                note=func.concat_ws('\n', MetaAuthKey.note, update_note) if key_obj.note else update_note,
                updated_at=now
            )
        )
        await db.commit()
        
        logger.warning(f"已过期的授权密钥: {key_obj.key_value}, {update_note}")
        
        if not exempt:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="授权密钥已过期"
            )
        
        return True
    except Exception as e:
        logger.error(f"更新过期密钥状态失败: {str(e)}", exc_info=True)
        await db.rollback()
        
        if not exempt:
            raise HTTPException(status_code=500, detail="处理密钥过期状态时出错")
        
        return True


async def _check_call_limit_exceeded(db: AsyncSession, request: Request, key_obj: MetaAuthKey,
                                   now: datetime, exempt: bool) -> bool:
    """检查密钥调用次数是否超限，如果超限则更新记录"""
    if key_obj.call_limit <= 0 or key_obj.call_count < key_obj.call_limit:
        return False
    
    # 调用次数已超限，收集详细信息
    context = _get_request_context(request, now)
    user_agent = request.headers.get("User-Agent", "unknown")
    referer = request.headers.get("Referer", "none")
    
    # 构建详细的安全日志信息
    security_log = {
        "event": "api_key_limit_exceeded",
        "key_value": key_obj.key_value,
        "key_id": str(key_obj.id),
        "app_id": str(key_obj.app_id) if key_obj.app_id else None,
        "user_id": str(key_obj.user_id) if key_obj.user_id else None,
        "time": context['time_str'],
        "trace_id": context['trace_id'],
        "path": context['path'],
        "method": context['method'],
        "ip_address": context['client_ip'],
        "user_agent": user_agent,
        "referer": referer,
        "call_count": key_obj.call_count,
        "call_limit": key_obj.call_limit
    }
    
    # 记录详细日志
    logger.warning(
        f"安全警告: 授权密钥调用次数超限: {key_obj.key_value}, IP: {context['client_ip']}, "
        f"路径: {context['method']} {context['path']}, "
        f"调用次数: {key_obj.call_count}/{key_obj.call_limit}",
        extra={"security_event": security_log}
    )
    
    # 更新数据库记录，添加安全事件信息
    security_note = (
        f"安全警告: 密钥超出调用限制。时间: {context['time_str']}, "
        f"请求ID: {context['trace_id']}, 路径: {context['method']} {context['path']}, "
        f"IP: {context['client_ip']}, User-Agent: {user_agent[:100]}..."
    )
    
    try:
        # 尝试记录安全事件到数据库
        await _update_security_event(db, key_obj, security_note, security_log, now)
        
        if not exempt:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API调用次数已达上限"
            )
        
        return True
    except HTTPException:
        # 如果是我们自己抛出的HTTPException，直接重新抛出
        raise
    except Exception as e:
        logger.error(f"记录调用次数超限事件失败: {str(e)}", exc_info=True)
        
        if not exempt:
            raise HTTPException(status_code=500, detail="处理调用限制时出错")
        
        return True


async def _update_security_event(db: AsyncSession, key_obj: MetaAuthKey, 
                               security_note: str, security_log: Dict[str, Any],
                               now: datetime):
    """更新数据库中的安全事件记录"""
    try:
        # 构造security_events数组的JSON字符串
        security_event_json = json.dumps([security_log])
        
        # 更新记录
        await db.execute(
            update(MetaAuthKey)
            .where(MetaAuthKey.id == key_obj.id)
            .values(
                note=func.concat_ws('\n', MetaAuthKey.note, security_note) if key_obj.note else security_note,
                updated_at=now,
                # 更新metadata中的security_events数组
                key_metadata=func.jsonb_set(
                    func.coalesce(MetaAuthKey.key_metadata, '{}'),
                    '{security_events}',
                    func.coalesce(
                        func.jsonb_path_query_array(
                            func.coalesce(MetaAuthKey.key_metadata, '{}'), 
                            '$.security_events[*]'
                        ),
                        '[]'
                    ) + security_event_json
                )
            )
        )
        await db.commit()
    except Exception as e:
        logger.error(f"更新安全事件记录失败: {str(e)}", exc_info=True)
        await db.rollback()
        raise


async def _update_call_count(db: AsyncSession, key_obj: MetaAuthKey):
    """更新密钥的调用次数"""
    try:
        await db.execute(
            update(MetaAuthKey)
            .where(MetaAuthKey.id == key_obj.id)
            .values(call_count=MetaAuthKey.call_count + 1)
        )
        await db.commit()
    except Exception as e:
        logger.error(f"更新调用次数失败: {str(e)}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="更新调用记录失败")


def _store_auth_info(request: Request, key_obj: MetaAuthKey):
    """将认证信息存储在请求状态中"""
    request.state.auth_key = key_obj.key_value
    request.state.auth_app_id = key_obj.app_id
    request.state.auth_user_id = key_obj.user_id


def _get_request_context(request: Request, now: datetime) -> Dict[str, Any]:
    """从请求中提取上下文信息"""
    return {
        'time_str': now.strftime("%Y-%m-%d %H:%M:%S"),
        'trace_id': getattr(request.state, "trace_key", str(uuid.uuid4())),
        'path': request.url.path,
        'method': request.method,
        'client_ip': request.client.host if hasattr(request, "client") else "unknown"
    }


def _check_api_call_success(result) -> bool:
    """
    检查API调用是否成功
    这里需要根据你的API返回结构来确定什么是"成功"
    """
    # 例如，如果你的API返回BaseResponse对象，可以检查code字段
    if hasattr(result, 'code'):
        return result.code == 200  # 或者其他表示成功的状态码
    
    # 如果返回的是dict，检查可能存在的code或status字段
    if isinstance(result, dict) and 'code' in result:
        return result['code'] == 200
    
    # 默认情况下，假设调用成功
    return True