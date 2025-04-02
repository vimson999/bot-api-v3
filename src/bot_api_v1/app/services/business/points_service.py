"""
积分服务模块

提供用户积分的查询、消费和管理功能。
"""
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime, timedelta
import uuid
import time
import asyncio
from enum import Enum

from sqlalchemy import select, update, and_, desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from sqlalchemy.orm import joinedload

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
from bot_api_v1.app.models.meta_user_points import MetaUserPoints
from bot_api_v1.app.models.rel_points_transaction import RelPointsTransaction
from bot_api_v1.app.models.meta_user import MetaUser
from bot_api_v1.app.services.business.user_cache_service import UserCacheService
from bot_api_v1.app.services.business.user_service import UserService

# 平台范围枚举
class PlatformScopeEnum(str, Enum):
    """平台范围枚举"""
    APP = "APP"
    API = "API"
    WECHAT = "wx"
    XIAOHONGSHU = "xhs"
    WEB = "web"
    MOBILE = "mobile"


# 交易类型枚举
class TransactionTypeEnum(str, Enum):
    """交易类型枚举"""
    PURCHASE = "PURCHASE"  # 购买
    CONSUME = "CONSUME"    # 消费
    EXPIRE = "EXPIRE"      # 过期
    ADJUST = "ADJUST"      # 调整
    REFUND = "REFUND"      # 退款


# 交易状态枚举
class TransactionStatusEnum(int, Enum):
    """交易状态枚举"""
    FAILED = 0       # 失败
    SUCCESS = 1      # 成功
    PROCESSING = 2   # 处理中


class PointsError(Exception):
    """积分操作过程中出现的错误"""
    
    def __init__(self, message: str, code: str = "POINTS_ERROR", details: Any = None):
        self.message = message
        self.code = code
        self.details = details
        super().__init__(message)


class UserNotFoundError(PointsError):
    """用户不存在异常"""
    
    def __init__(self, openid: str = None, user_id: str = None):
        details = {}
        if openid:
            details["openid"] = openid
        if user_id:
            details["user_id"] = user_id

        super().__init__(
            message="未找到用户信息，无法领取福利", 
            code="USER_NOT_FOUND",
            details=details
        )


class AlreadyClaimedError(PointsError):
    """已领取过积分异常"""
    
    def __init__(self, user_id: Union[str, uuid.UUID]):
        if isinstance(user_id, uuid.UUID):
            user_id = str(user_id)
            
        super().__init__(
            message="您已领取过积分奖励", 
            code="ALREADY_CLAIMED",
            details={"user_id": user_id}
        )


class SystemBusyError(PointsError):
    """系统繁忙异常"""
    
    def __init__(self, reason: str = None):
        details = {}
        if reason:
            details["reason"] = reason
            
        super().__init__(
            message="系统繁忙，请稍后再试", 
            code="SYSTEM_BUSY",
            details=details
        )


class PointsService:
    """积分服务，提供用户积分的管理和查询功能"""
    
    # 首次领取积分配置
    FIRST_TIME_POINTS_CONFIG = {
        "reward_amount": 1000,         # 首次奖励积分数量
        "expire_days": 365,            # 积分有效期（天）
        "transaction_type": TransactionTypeEnum.ADJUST,  # 交易类型
        "transaction_status": TransactionStatusEnum.SUCCESS,  # 交易状态
        "remark_template": "首次领取积分奖励 - {date}",  # 备注模板
        "gift_prefix": "GIFT",         # 交易编号前缀
        "max_retries": 3,              # 最大重试次数
        "lock_timeout": 5000,          # 行锁超时时间(毫秒)
        "backoff_factor": 0.1          # 重试退避因子
    }
    
    def __init__(self):
        """初始化积分服务"""
        self.user_service = UserService()  # 添加用户服务实例
    
    @gate_keeper()
    @log_service_call(method_type="points", tollgate="30-2")
    async def get_user_points(self, openid: str, db: AsyncSession) -> Dict[str, Any]:
        """
        获取用户积分信息
        
        Args:
            openid: 用户的OpenID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 包含用户积分信息的字典
            
        Raises:
            PointsError: 处理过程中出现的错误
        """
        trace_key = request_ctx.get_trace_key()
        
        try:
            # 查询用户信息
            user_query = select(MetaUser).where(
                MetaUser._open_id == openid,
                MetaUser.status == 1
            )
            user_result = await db.execute(user_query)
            user = user_result.scalar_one_or_none()
            
            if not user:
                raise PointsError("未找到您的用户信息，请重新关注公众号。")

            # 1. 查询用户积分账户
            stmt = select(MetaUserPoints).where(
                and_(
                    MetaUserPoints.user_id == user.id,
                    MetaUserPoints.status == 1
                )
            )
            result = await db.execute(stmt)
            points_account = result.scalar_one_or_none()
            
            # 2. 如果用户没有积分账户，创建一个新的账户
            if not points_account:
                logger.info(
                    f"用户积分账户不存在，创建新账户: {openid}",
                    extra={"request_id": trace_key, "openid": openid}
                )
                
                points_account = MetaUserPoints(
                    user_id=user.id,
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

            # 3. 构建返回结果
            result = {
                "user_id": user.id,
                "openid": user._open_id,
                "available_points": points_account.available_points
            }
            
            logger.info(
                f"获取用户积分成功: {openid}",
                extra={
                    "request_id": trace_key,
                    "openid": openid,
                    "available_points": points_account.available_points
                }
            )
            
            return result
            
        except PointsError as e:
            # 直接抛出业务异常
            raise
            
        except ValueError as e:
            error_msg = f"无效的用户ID格式: {str(e)}"
            logger.error(error_msg, extra={"request_id": trace_key})
            raise PointsError(error_msg)
            
        except Exception as e:
            error_msg = f"获取用户积分信息失败: {str(e)}"
            logger.error(
                error_msg,
                exc_info=True,
                extra={"request_id": trace_key, "openid": openid}
            )
            raise PointsError(error_msg)
    
    @gate_keeper()
    @log_service_call(method_type="points", tollgate="30-2")
    async def get_points_history(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 10,
        transaction_type: Optional[str] = None,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """
        获取用户积分交易历史
        
        Args:
            user_id: 用户ID
            page: 页码，从1开始
            page_size: 每页记录数量
            transaction_type: 交易类型筛选
            db: 数据库会话
            
        Returns:
            Dict: 包含分页后的交易记录和统计信息
            
        Raises:
            PointsError: 处理过程中出现的错误
        """
        trace_key = request_ctx.get_trace_key()
        
        try:
            # 将字符串ID转换为UUID
            user_uuid = uuid.UUID(user_id)
            
            # 构建查询条件
            conditions = [
                RelPointsTransaction.user_id == user_uuid,
                RelPointsTransaction.status == 1  # 只查询有效记录
            ]
            
            # 添加交易类型筛选
            if transaction_type:
                conditions.append(RelPointsTransaction.transaction_type == transaction_type)
            
            # 1. 查询总记录数
            count_stmt = select(func.count()).select_from(RelPointsTransaction).where(and_(*conditions))
            count_result = await db.execute(count_stmt)
            total_items = count_result.scalar_one()
            
            # 2. 计算总页数
            total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1
            
            # 3. 查询分页数据
            offset = (page - 1) * page_size
            
            records_stmt = select(RelPointsTransaction).where(
                and_(*conditions)
            ).order_by(
                desc(RelPointsTransaction.created_at)
            ).offset(offset).limit(page_size)
            
            records_result = await db.execute(records_stmt)
            records = records_result.scalars().all()
            
            # 在 get_points_history 方法中修改处理历史记录的部分
            # 4. 转换查询结果
            history_items = []
            for record in records:
                item = {
                    "transaction_id": str(record.id),
                    "transaction_no": record.transaction_no,
                    "transaction_type": record.transaction_type,
                    "transaction_status": record.transaction_status,
                    "points_change": record.points_change,
                    "remaining_points": record.remaining_points,
                    "api_name": getattr(record, 'api_name', None),
                    "api_path": getattr(record, 'api_path', None),
                    "remark": getattr(record, 'remark', ''),
                    "created_at": record.created_at.isoformat() if record.created_at else None
                }
                
                # 安全地获取 expire_time
                if hasattr(record, 'expire_time') and record.expire_time:
                    item["expire_time"] = record.expire_time.isoformat()
                else:
                    item["expire_time"] = None
                    
                history_items.append(item)
            
            # 5. 构建返回结果
            result = {
                "pagination": {
                    "current_page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "total_items": total_items
                },
                "items": history_items,
                "user_id": user_id
            }
            
            logger.info(
                f"查询用户积分历史成功: {user_id}",
                extra={
                    "request_id": trace_key,
                    "user_id": user_id,
                    "page": page,
                    "transaction_type": transaction_type or "all"
                }
            )
            
            return result
            
        except ValueError as e:
            # UUID格式错误
            error_msg = f"无效的用户ID格式: {str(e)}"
            logger.error(error_msg, extra={"request_id": trace_key})
            raise PointsError(error_msg)
            
        except Exception as e:
            error_msg = f"获取用户积分历史失败: {str(e)}"
            logger.error(
                error_msg,
                exc_info=True,
                extra={"request_id": trace_key, "user_id": user_id}
            )
            raise PointsError(error_msg)
    
    async def _generate_unique_transaction_no(self, db: AsyncSession, prefix: str = "GIFT") -> str:
        """
        生成唯一的交易编号
        
        Args:
            db: 异步数据库会话
            prefix: 交易编号前缀
            
        Returns:
            str: 唯一交易编号
        """
        timestamp = int(time.time())
        random_suffix = uuid.uuid4().hex[:8]
        transaction_no = f"{prefix}{timestamp}{random_suffix}"
        
        # 验证唯一性
        stmt = select(func.count()).select_from(RelPointsTransaction).where(
            RelPointsTransaction.transaction_no == transaction_no
        )
        
        result = await db.execute(stmt)
        if result.scalar_one() > 0:
            # 如果已存在，生成新的编号（避免递归过深）
            time.sleep(0.01)  # 等待10毫秒确保时间戳变化
            return await self._generate_unique_transaction_no(db, prefix)
        
        return transaction_no
    
    async def _check_existing_claim(
        self, 
        db: AsyncSession, 
        user_id: uuid.UUID,
        trace_key: str = None
    ) -> bool:
        """
        检查用户是否已经领取过首次积分奖励
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            trace_key: 请求追踪键
            
        Returns:
            bool: 如果已领取过返回True，否则返回False
        """
        # 使用与 remark_template 一致的模式进行查询
        remark_pattern = "首次领取积分奖励%"  # 使用更简单的模式匹配
        
        stmt = select(func.count()).select_from(RelPointsTransaction).where(
            and_(
                RelPointsTransaction.user_id == user_id,
                RelPointsTransaction.transaction_type == self.FIRST_TIME_POINTS_CONFIG["transaction_type"].value,
                RelPointsTransaction.remark.like(remark_pattern),
                RelPointsTransaction.status == 1  # 确保只检查有效记录
            )
        )
        
        try:
            result = await db.execute(stmt)
            return result.scalar_one() > 0
        except SQLAlchemyError as e:
            logger.error(
                f"检查用户首次领取积分记录失败: {str(e)}", 
                extra={"request_id": trace_key, "user_id": str(user_id)}
            )
            # 异常情况下，为安全起见返回True（认为已领取）
            return True
    
    async def _get_or_create_user_points(
        self, 
        db: AsyncSession, 
        user_id: uuid.UUID,
        trace_key: str = None
    ) -> Tuple[MetaUserPoints, bool]:
        """
        获取或创建用户积分账户
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            trace_key: 请求追踪键
            
        Returns:
            Tuple[MetaUserPoints, bool]: 用户积分账户对象和是否新创建的标志
        """
        # 使用FOR UPDATE行级锁，但移除不支持的timeout参数
        stmt = select(MetaUserPoints).where(
            and_(
                MetaUserPoints.user_id == user_id,
                MetaUserPoints.status == 1  # 确保只获取有效账户
            )
        ).with_for_update(skip_locked=True)  # 移除timeout参数
        
        # 其余代码保持不变
        result = await db.execute(stmt)
        user_points = result.scalar_one_or_none()
        
        created = False
        if not user_points:
            # 创建新的积分账户
            current_time = datetime.now()
            user_points = MetaUserPoints(
                user_id=user_id,
                total_points=0,
                available_points=0,
                frozen_points=0,
                used_points=0,
                expired_points=0,
                status=1,  # 设置状态为有效
                created_at=current_time,
                updated_at=current_time
            )
            db.add(user_points)
            await db.flush()
            
            logger.info(
                f"为用户创建了新的积分账户: {user_id}",
                extra={"request_id": trace_key, "user_id": str(user_id)}
            )
            created = True
        
        return user_points, created
    
    async def _create_points_transaction(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        points_change: int,
        remaining_points: int,
        transaction_type: Union[str, TransactionTypeEnum],
        expire_time: datetime,
        balance_snapshot: Dict[str, Any],
        remark: str,
        trace_key: str = None
    ) -> RelPointsTransaction:
        """
        创建积分交易记录
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            account_id: 账户ID
            points_change: 积分变动量
            remaining_points: 剩余积分
            transaction_type: 交易类型
            expire_time: 过期时间
            balance_snapshot: 余额快照
            remark: 备注
            trace_key: 请求追踪键
            
        Returns:
            RelPointsTransaction: 创建的交易记录对象
        """
        # 处理枚举类型
        if isinstance(transaction_type, TransactionTypeEnum):
            transaction_type = transaction_type.value
        
        transaction_status = self.FIRST_TIME_POINTS_CONFIG["transaction_status"].value
        
        # 生成唯一交易编号
        transaction_no = await self._generate_unique_transaction_no(
            db, 
            self.FIRST_TIME_POINTS_CONFIG["gift_prefix"]
        )
        
        current_time = datetime.now()
        
        # 创建交易记录 - 确保所有必要字段都被设置
        transaction_data = {
            "transaction_no": transaction_no,
            "user_id": user_id,
            "account_id": account_id,
            "points_change": points_change,
            "remaining_points": remaining_points,
            "transaction_type": transaction_type,
            "transaction_status": transaction_status,
            "expire_time": expire_time,
            "remark": remark,
            "created_at": current_time,
            "status": 1  # 设置记录状态为有效
        }
        
        # 如果模型支持 balance_snapshot 字段，则添加
        try:
            transaction = RelPointsTransaction(**transaction_data)
            if hasattr(transaction, 'balance_snapshot'):
                transaction.balance_snapshot = balance_snapshot
        except TypeError as e:
            # 如果构造函数不接受某些参数，记录错误并移除不支持的字段
            logger.warning(
                f"创建积分交易记录时遇到字段不匹配问题: {str(e)}",
                extra={"request_id": trace_key, "user_id": str(user_id)}
            )
            # 移除可能不支持的字段
            if 'balance_snapshot' in transaction_data:
                del transaction_data['balance_snapshot']
            transaction = RelPointsTransaction(**transaction_data)
        
        db.add(transaction)
        await db.flush()
        
        logger.info(
            f"创建积分交易记录成功: {transaction_no}, 用户: {user_id}, 变动: {points_change}",
            extra={
                "request_id": trace_key,
                "user_id": str(user_id),
                "transaction_no": transaction_no,
                "points_change": points_change
            }
        )
        
        return transaction
    
    async def _update_user_points(
            self,
            db: AsyncSession,
            user_points: MetaUserPoints,
            points_to_add: int,
            trace_key: str = None
        ) -> MetaUserPoints:
        """
        更新用户积分
        
        Args:
            db: 异步数据库会话
            user_points: 用户积分账户对象
            points_to_add: 要添加的积分数量
            trace_key: 请求追踪键
            
        Returns:
            MetaUserPoints: 更新后的用户积分账户对象
        """
        current_time = datetime.now()
        
        # 计算新值
        new_total = user_points.total_points + points_to_add
        new_available = user_points.available_points + points_to_add
        
        # 执行更新操作
        stmt = (
            update(MetaUserPoints)
            .where(MetaUserPoints.id == user_points.id)
            .values(
                total_points=new_total,
                available_points=new_available,
                last_earn_time=current_time,
                updated_at=current_time
            )
            .returning(MetaUserPoints)
        )
        
        try:
            result = await db.execute(stmt)
            updated_points = result.scalar_one()
            
            # 更新对象状态
            user_points.total_points = new_total
            user_points.available_points = new_available
            user_points.last_earn_time = current_time
            user_points.updated_at = current_time
            
            logger.info(
                f"更新用户积分成功: {user_points.user_id}, 增加: {points_to_add}, 当前可用: {new_available}",  # 修复拼写错误：user__id -> user_id
                extra={
                    "request_id": trace_key,
                    "user_id": str(user_points.user_id),
                    "points_added": points_to_add,
                    "available_points": new_available
                }
            )
            
            return updated_points
        except SQLAlchemyError as e:
            logger.error(
                f"更新用户积分失败: {str(e)}",
                extra={"request_id": trace_key, "user_id": str(user_points.user_id)}
            )
            raise


    @gate_keeper()
    @log_service_call(method_type="points", tollgate="30-3")
    async def claim_first_time_points(
        self,
        openid: str,
        db: AsyncSession,
        platform_scope: Union[str, PlatformScopeEnum] = PlatformScopeEnum.WECHAT,
    ) -> Dict[str, Any]:
        """
        用户首次点击领取积分奖励
        
        Args:
            openid: 用户OpenID
            db: 数据库会话
            platform_scope: 平台范围，默认为微信
            
        Returns:
            Dict[str, Any]: 操作结果，格式为 
                {"success": bool, "message": str, "data": Optional[Dict], "code": Optional[str]}
        
        Raises:
            PointsError: 积分操作错误
        """
        trace_key = request_ctx.get_trace_key()
        operation_id = uuid.uuid4()
        start_time = time.time()
        
        # 使用配置参数
        reward_points = self.FIRST_TIME_POINTS_CONFIG["reward_amount"]
        expire_days = self.FIRST_TIME_POINTS_CONFIG["expire_days"]
        retries = 0
        max_retries = self.FIRST_TIME_POINTS_CONFIG["max_retries"]
        backoff_factor = self.FIRST_TIME_POINTS_CONFIG["backoff_factor"]
        
        # 日志记录操作开始
        logger.info(
            f"[{operation_id}] 开始处理用户首次领取积分: {openid[:5]}***",
            extra={"request_id": trace_key, "openid": openid, "operation_id": str(operation_id)}
        )
        
        # 处理平台范围参数
        if isinstance(platform_scope, PlatformScopeEnum):
            platform_scope = platform_scope.value
        
        try:
            # 修改：在事务外查询用户ID
            user_id = await self.user_service.get_user_id_by_openid(
                db, 
                openid, 
                platform_scope, 
                trace_key, 
                str(operation_id)
            )
            
            if not user_id:
                logger.warning(
                    f"[{operation_id}] 未找到用户信息，无法领取福利: {openid[:5]}***",
                    extra={
                        "request_id": trace_key, 
                        "openid": openid,
                        "platform_scope": platform_scope
                    }
                )
                return {"success": False, "message": "未找到用户信息，无法领取福利", "code": "USER_NOT_FOUND"}
            
            # 使用重试机制处理并发冲突
            while retries < max_retries:
                try:
                    # 修改：创建新的数据库会话用于事务，避免使用已有事务的会话
                    async with db.begin_nested() as nested:  # 使用嵌套事务
                        # 2. 检查是否已领取过
                        existing_claim = await self._get_existing_claim(db, user_id, trace_key)
                        if existing_claim:
                            claim_time = existing_claim.created_at.strftime("%Y-%m-%d %H:%M")
                            logger.info(
                                f"[{operation_id}] 用户已领取过积分奖励: {user_id}, 领取时间: {claim_time}",
                                extra={
                                    "request_id": trace_key, 
                                    "user_id": str(user_id),
                                    "claim_time": claim_time
                                }
                            )
                            return {
                                "success": False, 
                                "message": f"您已于 {claim_time} 领取过积分奖励", 
                                "code": "ALREADY_CLAIMED",
                                "data": {
                                    "claim_time": claim_time
                                }
                            }
                        
                        # 3. 获取或创建用户积分账户
                        user_points, is_new = await self._get_or_create_user_points(db, user_id, trace_key)
                        
                        # 4. 计算新的积分值和过期时间
                        current_time = datetime.now()
                        expire_time = current_time + timedelta(days=expire_days)
                        
                        # 5. 更新用户积分账户
                        await self._update_user_points(db, user_points, reward_points, trace_key)
                        
                        # 6. 准备余额快照
                        balance_snapshot = {
                            "total_points": user_points.total_points,
                            "available_points": user_points.available_points,
                            "frozen_points": user_points.frozen_points,
                            "used_points": user_points.used_points,
                            "expired_points": user_points.expired_points,
                            "reward_date": current_time.isoformat(),
                            "operation": "first_time_reward",
                            "operation_id": str(operation_id),
                            "trace_key": trace_key
                        }
                        
                        # 7. 创建交易记录
                        remark = self.FIRST_TIME_POINTS_CONFIG["remark_template"].format(
                            date=current_time.strftime("%Y-%m-%d")
                        )
                        transaction = await self._create_points_transaction(
                            db=db,
                            user_id=user_id,
                            account_id=user_points.id,
                            points_change=reward_points,
                            remaining_points=user_points.available_points,
                            transaction_type=self.FIRST_TIME_POINTS_CONFIG["transaction_type"],
                            expire_time=expire_time,
                            balance_snapshot=balance_snapshot,
                            remark=remark,
                            trace_key=trace_key
                        )
                    
                    # 提交外部事务
                    await db.commit()
                        
                    # 8. 记录成功日志
                    elapsed = time.time() - start_time
                    logger.info(
                        f"[{operation_id}] 用户首次领取积分成功: {user_id}, 奖励: {reward_points}积分, "
                        f"耗时: {elapsed:.2f}s",
                        extra={
                            "request_id": trace_key,
                            "user_id": str(user_id),
                            "points_added": reward_points,
                            "current_points": user_points.available_points,
                            "elapsed_time": elapsed,
                            "transaction_no": transaction.transaction_no
                        }
                    )
                    
                    # 9. 返回成功结果
                    return {
                        "success": True, 
                        "message": f"恭喜您获得{reward_points}积分奖励！", 
                        "data": {
                            "points_added": reward_points,
                            "current_points": user_points.available_points,
                            "transaction_no": transaction.transaction_no,
                            "expire_time": expire_time.isoformat()
                        }
                    }
                    
                except OperationalError as e:
                    # 数据库锁超时或死锁，可以重试
                    retries += 1
                    if retries < max_retries:
                        await db.rollback()
                        logger.warning(
                            f"[{operation_id}] 数据库锁冲突，正在重试 {retries}/{max_retries}: {str(e)}",
                            extra={"request_id": trace_key, "error": str(e)}
                        )
                        # 指数退避策略
                        await asyncio.sleep(backoff_factor * (2 ** retries))
                    else:
                        logger.error(
                            f"[{operation_id}] 数据库锁冲突达到最大重试次数: {str(e)}",
                            extra={"request_id": trace_key, "error": str(e)}
                        )
                        raise SystemBusyError(f"数据库锁冲突: {str(e)}")
                    
                except IntegrityError as e:
                    # 完整性错误，通常是唯一约束或外键约束违反
                    if "unique constraint" in str(e).lower() and "transaction_no" in str(e).lower():
                        # 可能是交易编号重复，可以重试
                        retries += 1
                        if retries < max_retries:
                            await db.rollback()
                            logger.warning(
                                f"[{operation_id}] 交易编号冲突，正在重试: {str(e)}",
                                extra={"request_id": trace_key, "error": str(e)}
                            )
                            continue
                        
                        logger.error(
                            f"[{operation_id}] 数据库完整性错误: {str(e)}",
                            extra={"request_id": trace_key, "error": str(e)}
                        )
                        await db.rollback()
                        raise PointsError("操作失败，请稍后再试", "DATABASE_ERROR")
                
                except SQLAlchemyError as e:
                    # 修改：捕获所有SQLAlchemy错误
                    retries += 1
                    if retries < max_retries:
                        await db.rollback()
                        logger.warning(
                            f"[{operation_id}] 数据库错误，正在重试 {retries}/{max_retries}: {str(e)}",
                            extra={"request_id": trace_key, "error": str(e)}
                        )
                        await asyncio.sleep(backoff_factor * (2 ** retries))
                    else:
                        logger.error(
                            f"[{operation_id}] 数据库错误达到最大重试次数: {str(e)}",
                            extra={"request_id": trace_key, "error": str(e)}
                        )
                        await db.rollback()
                        return {"success": False, "message": "系统繁忙，请稍后再试", "code": "DATABASE_ERROR"}
            
            # 如果所有重试都失败了
            if retries >= max_retries:
                logger.error(
                    f"[{operation_id}] 首次领取积分失败，已达最大重试次数",
                    extra={"request_id": trace_key, "openid": openid}
                )
                return {"success": False, "message": "系统繁忙，请稍后再试", "code": "MAX_RETRIES_REACHED"}
                
        except UserNotFoundError as e:
            # 用户不存在错误
            logger.warning(
                f"[{operation_id}] {e.message}: {e.details}",
                extra={"request_id": trace_key, "details": e.details}
            )
            return {"success": False, "message": e.message, "code": e.code}
            
        except AlreadyClaimedError as e:
            # 已领取过错误
            logger.info(
                f"[{operation_id}] {e.message}: {e.details}",
                extra={"request_id": trace_key, "details": e.details}
            )
            return {"success": False, "message": e.message, "code": e.code}
            
        except SystemBusyError as e:
            # 系统繁忙错误
            logger.error(
                f"[{operation_id}] {e.message}: {e.details}",
                extra={"request_id": trace_key, "details": e.details}
            )
            return {"success": False, "message": e.message, "code": e.code}
            
        except SQLAlchemyError as e:
            # 数据库错误
            error_msg = f"数据库操作失败: {str(e)}"
            logger.error(
                f"[{operation_id}] {error_msg}",
                exc_info=True,
                extra={"request_id": trace_key, "openid": openid}
            )
            await db.rollback()
            return {"success": False, "message": "系统繁忙，请稍后再试", "code": "DATABASE_ERROR"}
            
        except Exception as e:
            # 其他未预期的错误
            error_msg = f"首次领取积分失败: {str(e)}"
            logger.error(
                f"[{operation_id}] {error_msg}",
                exc_info=True,
                extra={"request_id": trace_key, "openid": openid}
            )
            await db.rollback()
            return {"success": False, "message": "操作失败，请稍后再试", "code": "UNKNOWN_ERROR"}
            
        finally:
            # 记录操作完成
            elapsed = time.time() - start_time
            logger.info(
                f"[{operation_id}] 首次领取积分操作完成，耗时: {elapsed:.2f}s",
                extra={"request_id": trace_key, "elapsed_time": elapsed, "openid": openid[:5] + "***"}
            )

    async def _get_existing_claim(
        self, 
        db: AsyncSession, 
        user_id: uuid.UUID,
        trace_key: str = None
    ) -> Optional[RelPointsTransaction]:
        """
        获取用户首次领取积分记录（如果存在）
        
        Args:
            db: 异步数据库会话
            user_id: 用户ID
            trace_key: 请求追踪键
            
        Returns:
            Optional[RelPointsTransaction]: 如果存在返回交易记录对象，否则返回None
        """
        remark_pattern = "首次领取积分奖励%"
        
        stmt = select(RelPointsTransaction).where(
            and_(
                RelPointsTransaction.user_id == user_id,
                RelPointsTransaction.transaction_type == self.FIRST_TIME_POINTS_CONFIG["transaction_type"].value,
                RelPointsTransaction.remark.like(remark_pattern),
                RelPointsTransaction.status == 1
            )
        ).order_by(desc(RelPointsTransaction.created_at)).limit(1)
        
        try:
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(
                f"查询用户首次领取积分记录失败: {str(e)}", 
                extra={"request_id": trace_key, "user_id": str(user_id)}
            )
            return None