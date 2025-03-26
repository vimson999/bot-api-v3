"""
积分服务模块

提供用户积分的查询、消费和管理功能。
"""
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import uuid

from sqlalchemy import select, update, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
from bot_api_v1.app.models.meta_user_points import MetaUserPoints
from bot_api_v1.app.models.rel_points_transaction import RelPointsTransaction


class PointsError(Exception):
    """积分操作过程中出现的错误"""
    pass


class PointsService:
    """积分服务，提供用户积分的管理和查询功能"""
    
    def __init__(self):
        """初始化积分服务"""
        pass
    
    @gate_keeper()
    @log_service_call(method_type="points", tollgate="30-2")
    async def get_user_points(self, user_id: str, db: AsyncSession) -> Dict[str, Any]:
        """
        获取用户积分信息
        
        Args:
            user_id: 用户ID
            db: 数据库会话
            
        Returns:
            Dict: 包含用户积分信息的字典
            
        Raises:
            PointsError: 处理过程中出现的错误
        """
        trace_key = request_ctx.get_trace_key()
        
        try:
            # 将字符串ID转换为UUID
            user_uuid = uuid.UUID(user_id)
            
            # 1. 查询用户积分账户
            stmt = select(MetaUserPoints).where(
                and_(
                    MetaUserPoints.user_id == user_uuid,
                    MetaUserPoints.status == 1
                )
            )
            result = await db.execute(stmt)
            points_account = result.scalar_one_or_none()
            
            # 2. 如果用户没有积分账户，创建一个新的账户
            if not points_account:
                logger.info(
                    f"用户积分账户不存在，创建新账户: {user_id}",
                    extra={"request_id": trace_key, "user_id": user_id}
                )
                
                points_account = MetaUserPoints(
                    user_id=user_uuid,
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
            
            # 3. 获取即将过期的积分
            now = datetime.now()
            thirty_days_later = now + timedelta(days=30)
            
            expiring_soon_stmt = select(
                RelPointsTransaction.id,
                RelPointsTransaction.points_change,
                RelPointsTransaction.remaining_points,
                RelPointsTransaction.expire_time,
                RelPointsTransaction.remark
            ).where(
                and_(
                    RelPointsTransaction.user_id == user_uuid,
                    RelPointsTransaction.transaction_type == "PURCHASE",
                    RelPointsTransaction.transaction_status == 1,  # 成功状态
                    RelPointsTransaction.points_change > 0,  # 积分增加的交易
                    RelPointsTransaction.expire_time > now,  # 未过期
                    RelPointsTransaction.expire_time <= thirty_days_later,  # 30天内过期
                )
            ).order_by(RelPointsTransaction.expire_time)
            
            expiring_result = await db.execute(expiring_soon_stmt)
            expiring_records = expiring_result.fetchall()
            
            # 4. 构建返回数据
            expiring_soon_list = []
            for record in expiring_records:
                expiring_soon_list.append({
                    "transaction_id": str(record.id),
                    "points": record.points_change,
                    "expire_time": record.expire_time.isoformat() if record.expire_time else None,
                    "remark": record.remark
                })
            
            last_update = None
            if points_account.last_earn_time and points_account.last_consume_time:
                last_update = max(points_account.last_earn_time, points_account.last_consume_time)
            elif points_account.last_earn_time:
                last_update = points_account.last_earn_time
            elif points_account.last_consume_time:
                last_update = points_account.last_consume_time
                
            result = {
                "total_points": points_account.total_points,
                "available_points": points_account.available_points,
                "frozen_points": points_account.frozen_points,
                "used_points": points_account.used_points,
                "expired_points": points_account.expired_points,
                "last_update": last_update.isoformat() if last_update else None,
                "expiring_soon": expiring_soon_list,
                "account_id": str(points_account.id)
            }
            
            logger.info(
                f"获取用户积分成功: {user_id}",
                extra={
                    "request_id": trace_key,
                    "user_id": user_id,
                    "available_points": points_account.available_points
                }
            )
            
            return result
            
        except ValueError as e:
            # UUID格式错误
            error_msg = f"无效的用户ID格式: {str(e)}"
            logger.error(error_msg, extra={"request_id": trace_key})
            raise PointsError(error_msg)
            
        except Exception as e:
            error_msg = f"获取用户积分信息失败: {str(e)}"
            logger.error(
                error_msg,
                exc_info=True,
                extra={"request_id": trace_key, "user_id": user_id}
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
            
            # 4. 转换查询结果
            history_items = []
            for record in records:
                history_items.append({
                    "transaction_id": str(record.id),
                    "transaction_no": record.transaction_no,
                    "transaction_type": record.transaction_type,
                    "transaction_status": record.transaction_status,
                    "points_change": record.points_change,
                    "remaining_points": record.remaining_points,
                    "api_name": record.api_name,
                    "api_path": record.api_path,
                    "expire_time": record.expire_time.isoformat() if record.expire_time else None,
                    "remark": record.remark,
                    "created_at": record.created_at.isoformat() if record.created_at else None
                })
            
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