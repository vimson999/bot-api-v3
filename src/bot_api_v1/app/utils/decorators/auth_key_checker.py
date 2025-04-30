import uuid
import json
from functools import wraps
from typing import Optional, Dict, Any, Callable, Union
from datetime import datetime, timedelta

from fastapi import Header, HTTPException, Depends, Request, status
from sqlalchemy import select, update, and_, func, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from bot_api_v1.app.models import relations
from bot_api_v1.app.models.meta_auth_key import MetaAuthKey
from bot_api_v1.app.models.meta_user_points import MetaUserPoints
from bot_api_v1.app.models.rel_points_transaction import RelPointsTransaction
from bot_api_v1.app.db.session import get_db, async_session_maker
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
import time  # 确保导入time模块
from bot_api_v1.app.core.schemas import BaseResponse


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
                # 确保db不为None再调用_validate_key
                key_obj = await _validate_key(db, auth_key, exempt) if db else None
                if not key_obj:
                    if exempt:
                        return await func(*args, **kwargs)
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="无效的授权密钥"
                    )

                request_ctx.set_cappa_user_id(str(key_obj.user_id))
                
                # 步骤6：检查密钥状态
                now = datetime.now()
                
                # 检查过期状态
                if db and await _check_key_expired(db, request, key_obj, now, exempt):
                    return await func(*args, **kwargs) if exempt else None
                
                # 步骤7：检查用户积分
                if db and await _check_user_points(db, request, key_obj, exempt):
                    return await func(*args, **kwargs) if exempt else None
                
                # 步骤8：执行原始函数
                result = await func(*args, **kwargs)
                
                # 步骤9：检查调用是否成功
                is_successful = _check_api_call_success(result)
                
                # 步骤10：只有在成功时才扣减积分
                if is_successful and db and key_obj:
                    await _update_user_points(db, key_obj, request)
                    logger.info(f"API调用成功，执行积分扣减")
                elif not is_successful:
                    logger.info(f"API调用返回业务失败，不扣除积分")
                
                # 返回原始函数的结果
                return result
            except Exception as e:
                # 函数执行失败，记录错误但不扣除积分
                logger.error(f"API执行异常，不扣除积分: {str(e)}", exc_info=True)
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
    # 确保比较的两个时间对象类型一致
    if not key_obj.expired_at:
        return False
        
    # 检查是否为带时区的日期时间
    if key_obj.expired_at.tzinfo is not None and now.tzinfo is None:
        # 如果expired_at有时区而now没有，将now转换为naive
        expired_at_naive = key_obj.expired_at.replace(tzinfo=None)
        if now <= expired_at_naive:
            return False
    elif key_obj.expired_at.tzinfo is None and now.tzinfo is not None:
        # 如果now有时区而expired_at没有，将expired_at转换为aware
        now_naive = now.replace(tzinfo=None)
        if now_naive <= key_obj.expired_at:
            return False
    else:
        # 两者时区状态一致，直接比较
        if now <= key_obj.expired_at:
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


async def _check_user_points(db: AsyncSession, request: Request, key_obj: MetaAuthKey, exempt: bool) -> bool:
    """检查用户积分是否存在
    
    这个函数仅检查用户是否有积分账户，不检查具体的积分数量。
    具体的积分扣减验证会在业务处理过程中进行。
    
    Args:
        db: 数据库会话
        request: 请求对象
        key_obj: 认证密钥对象
        exempt: 是否豁免验证
        
    Returns:
        bool: 如果需要中止请求处理则返回True，否则返回False
    """
    # 获取用户ID
    user_id = key_obj.user_id
    if not user_id:
        error_msg = "API密钥未关联任何用户账户，无法处理积分"
        logger.error(error_msg)
        if not exempt:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_msg
            )
        return True
    
    try:
        root_trace_key = request_ctx.get_root_trace_key()
        trace_key = request_ctx.get_trace_key()

        # 查询用户积分账户
        stmt = select(MetaUserPoints).where(
            and_(
                MetaUserPoints.user_id == user_id,
                MetaUserPoints.status == 1
            )
        )
        result = await db.execute(stmt)
        points_account = result.scalar_one_or_none()

        # 如果用户没有积分账户，创建一个
        if not points_account:
            logger.info(f"用户积分账户不存在，正在创建: {user_id}")
            
            # 创建积分账户
            points_account = MetaUserPoints(
                user_id=user_id,
                total_points=0,
                available_points=0,
                frozen_points=0,
                used_points=0,
                expired_points=0,
                status=1
            )
            db.add(points_account)
            await db.commit()
            await db.refresh(points_account)
            
            logger.info_to_db(f"已创建用户积分账户: {points_account.id}",
                extra={
                    "request_id": trace_key,
                    "root_trace_key": root_trace_key
                }
            )
            
            # 如果账户余额为0，提示用户充值
            error_msg = "您的积分账户余额为0，请先充值后再使用服务"
            logger.info_to_db(error_msg,
                extra={
                    "request_id": trace_key,
                    "root_trace_key": root_trace_key
                }
            )
            if not exempt:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=error_msg
                )
                # return BaseResponse(
                #     code=status.HTTP_402_PAYMENT_REQUIRED,
                #     message=error_msg,
                #     data=None
                # )
            return True
        
        # 如果账户余额为0，提示用户充值
        if points_account.available_points <= 0:
            error_msg = "您的积分账户余额不足，请先充值后再使用服务"
            logger.info_to_db(error_msg,
                extra={
                    "request_id": trace_key,
                    "root_trace_key": root_trace_key
                }
            )

            if not exempt:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail=error_msg
                )
                # return BaseResponse(
                #     code=status.HTTP_402_PAYMENT_REQUIRED,
                #     message=error_msg,
                #     data=None
                # )
            return True
        
        # 将积分信息存入上下文
        request_ctx.set_points_info(
            account_id=str(points_account.id),
            available_points=points_account.available_points,
            user_id=str(user_id)
        )
        
        logger.info_to_db(f"用户积分账户正常: ID={points_account.id}, 可用积分={points_account.available_points}",
            extra={
                "request_id": trace_key,
                "root_trace_key": root_trace_key
            }
        )

        return False
        
    except HTTPException:
        # 直接重新抛出HTTP异常
        raise
    except Exception as e:
        error_msg = f"检查用户积分失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        if not exempt:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="检查用户积分时发生错误"
            )
        return True


async def _update_user_points(db: AsyncSession, key_obj: MetaAuthKey, request: Request) -> bool:
    """更新用户积分，执行积分扣减
    
    Args:
        db: 数据库会话
        key_obj: 认证密钥对象
        request: 请求对象
    
    Returns:
        bool: 操作是否成功
    """
    # 获取积分信息
    points_info = request_ctx.get_points_info()
    consumed_points = points_info.get('consumed_points', 0)
    account_id = points_info.get('account_id')
    available_points = points_info.get('available_points', 0)
    user_id = points_info.get('user_id')
    api_name = points_info.get('api_name', "未知API")
    root_trace_key = request_ctx.get_root_trace_key()
    trace_key = request_ctx.get_trace_key()
    
    # 如果没有积分消耗或缺少账户ID，跳过处理
    if not consumed_points or not account_id or not user_id:
        logger.info_to_db(f"无需扣减积分: consumed_points={consumed_points}, account_id={account_id}",
            extra={
                "request_id": trace_key,
                "root_trace_key": root_trace_key
            }
        )
        return False
    
    # 不能消耗超过用户可用积分
    if consumed_points > available_points:
        logger.warning(f"消耗积分({consumed_points})超过可用积分({available_points})，将限制为可用积分")
        consumed_points = available_points
    
    try:
        # 获取请求路径和IP
        api_path = request.url.path
        client_ip = request.client.host if hasattr(request, "client") else "unknown"
        request_id = getattr(request.state, "trace_key", request_ctx.get_trace_key())
        
        # 转换UUID字符串为UUID对象
        try:
            account_uuid = uuid.UUID(account_id)
            user_uuid = uuid.UUID(user_id)
        except ValueError as e:
            logger.error(f"无效的UUID格式: {e}")
            return False

        # 检查数据库会话是否已经在事务中
        in_transaction = db.in_transaction()
        if in_transaction:
            # 1. 更新用户积分账户
            update_result = await db.execute(
                update(MetaUserPoints)
                .where(MetaUserPoints.id == account_uuid)
                .values(
                    available_points=MetaUserPoints.available_points - consumed_points,
                    total_points=MetaUserPoints.total_points - consumed_points,
                    used_points=MetaUserPoints.used_points + consumed_points,
                    last_consume_time=datetime.now()
                )
            )
            
            if update_result.rowcount == 0:
                logger.error(f"更新积分账户失败: 找不到ID为 {account_id} 的账户")
                return False
                
            # 2. 生成交易编号
            import time  # 确保导入time模块
            transaction_no = f"TX{int(time.time())}{str(uuid.uuid4())[-12:]}"
            
            # 3. 创建积分交易记录
            transaction = RelPointsTransaction(
                transaction_no=transaction_no,
                user_id=user_uuid,
                account_id=account_uuid,
                points_change=-consumed_points,  # 负值表示消费
                remaining_points=available_points - consumed_points,
                transaction_type="CONSUME",
                transaction_status=1,  # 成功
                api_name=api_name,
                api_path=api_path,
                request_id=request_id,
                expire_time=datetime.now() + timedelta(days=365),  # 默认一年后过期
                remark=f"API调用消费: {api_name}",
                related_api_key_id=key_obj.id,
                status=1,
                client_ip=client_ip
            )
            db.add(transaction)
        else:
            # 如果不在事务中，使用begin()开始新事务
            async with db.begin():
                # 1. 更新用户积分账户
                update_result = await db.execute(
                    update(MetaUserPoints)
                    .where(MetaUserPoints.id == account_uuid)
                    .values(
                        available_points=MetaUserPoints.available_points - consumed_points,
                        used_points=MetaUserPoints.used_points + consumed_points,
                        total_points=MetaUserPoints.total_points - consumed_points,
                        last_consume_time=datetime.now()
                    )
                )
                
                if update_result.rowcount == 0:
                    logger.error(f"更新积分账户失败: 找不到ID为 {account_id} 的账户")
                    return False
                    
                # 2. 生成交易编号
                import time  # 确保导入time模块
                transaction_no = f"TX{int(time.time())}{str(uuid.uuid4())[-12:]}"
                
                # 3. 创建积分交易记录
                transaction = RelPointsTransaction(
                    transaction_no=transaction_no,
                    user_id=user_uuid,
                    account_id=account_uuid,
                    points_change=-consumed_points,  # 负值表示消费
                    remaining_points=available_points - consumed_points,
                    transaction_type="CONSUME",
                    transaction_status=1,  # 成功
                    api_name=api_name,
                    api_path=api_path,
                    request_id=request_id,
                    expire_time=datetime.now() + timedelta(days=365),  # 默认一年后过期
                    remark=f"API调用消费: {api_name}",
                    related_api_key_id=key_obj.id,
                    status=1,
                    client_ip=client_ip
                )
                db.add(transaction)
        
        logger.info_to_db(f"积分扣减成功: 用户 {user_id}, 消耗 {consumed_points} 积分, 剩余 {available_points - consumed_points} 可用积分",
            extra={
                "request_id": trace_key,
                "root_trace_key": root_trace_key
            }
        )
        return True
        
    except SQLAlchemyError as e:
        logger.error(f"积分扣减数据库错误: {str(e)}", exc_info=True)
        if not db.in_transaction():
            # 只有在我们自己开启的事务中才回滚
            await db.rollback()
        return False
    except Exception as e:
        logger.error(f"积分扣减未知错误: {str(e)}", exc_info=True)
        if not db.in_transaction():
            # 只有在我们自己开启的事务中才回滚
            await db.rollback()
        return False


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