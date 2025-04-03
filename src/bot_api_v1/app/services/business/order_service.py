"""
订单服务模块

提供订单的创建、查询、支付等功能。
"""
import uuid
import time
import secrets
from typing import Dict, Any, Optional, List
from datetime import datetime

from sqlalchemy import select, update, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
from bot_api_v1.app.models.meta_order import MetaOrder
from bot_api_v1.app.models.meta_product import MetaProduct


class OrderError(Exception):
    """订单操作过程中出现的错误"""
    pass


class OrderService:
    """订单服务，提供订单的创建、查询、支付等功能"""
    
    def __init__(self):
        """初始化订单服务"""
        pass
    
    @gate_keeper()
    @log_service_call(method_type="order", tollgate="30-1")
    async def create_order(
        self, 
        user_id: str, 
        openid: str, 
        product_id: str, 
        product_name: str,
        amount: float, 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        创建订单
        
        Args:
            user_id: 用户ID
            openid: 用户OpenID
            product_id: 商品ID
            product_name: 商品名称
            amount: 支付金额
            db: 数据库会话
            
        Returns:
            Dict: 包含订单信息的字典
        """
        trace_key = request_ctx.get_trace_key()
        logger.info(f"创建订单: user_id={user_id}, product_id={product_id}", 
                    extra={"request_id": trace_key})
        
        try:
            # 生成订单号
            order_no = f"WX{int(time.time())}{secrets.randbelow(10000):04d}"
            
            # 创建订单记录
            new_order = {}
            # new_order = MetaOrder(
            #     order_no=order_no,  # 订单编号，由时间戳和随机数生成
            #     order_type="PACKAGE",  # 或根据商品类型设置
            #     user_id=uuid.UUID(user_id),
            #     product_id=uuid.UUID(product_id),
            #     original_amount=amount,
            #     discount_amount=0,  # 可根据促销活动设置
            #     total_amount=amount,
            #     total_points=0,  # 根据商品设置
            #     currency="CNY",
            #     order_status=0,  # 待支付
            #     payment_channel="WECHAT",
            #     user_name=None,  # 可从用户信息获取
            #     product_snapshot={
            #         "name": product_name,
            #         "price": amount,
            #         "id": product_id
            #     },
            #     client_ip=request_ctx.get_context().get("ip_address") or "127.0.0.1",  # 添加默认值并修复逗号
            #     remark=f"微信公众号购买 {product_name}"
            # )
            
            # db.add(new_order)
            await db.commit()
            await db.refresh(new_order)
            
            return {
                # "order_id": str(new_order.id),
                "order_no": order_no,
                "amount": amount,
                "product_name": product_name
            }
            
        except Exception as e:
            await db.rollback()
            logger.error(f"创建订单失败: {str(e)}", 
                        exc_info=True, 
                        extra={"request_id": trace_key})
            raise OrderError(f"创建订单失败: {str(e)}")
    
    @gate_keeper()
    @log_service_call(method_type="order", tollgate="30-2")
    async def get_order_info(self, order_id: str, db: AsyncSession):
        """
        获取订单信息
        
        Args:
            order_id: 订单ID
            db: 数据库会话
            
        Returns:
            MetaOrder: 订单对象
        """
        trace_key = request_ctx.get_trace_key()
        
        try:
            # 查询订单信息
            order_query = select(MetaOrder).where(
                MetaOrder.id == uuid.UUID(order_id)
            )
            result = await db.execute(order_query)
            order = result.scalar_one_or_none()
            
            return order
            
        except Exception as e:
            logger.error(f"获取订单信息失败: {str(e)}", 
                        exc_info=True, 
                        extra={"request_id": trace_key})
            return None
    
       
    @gate_keeper()
    @log_service_call(method_type="order", tollgate="30-3")
    async def update_order_status(
        self, 
        order_id: str, 
        status: int, 
        db: AsyncSession,
        transaction_id: Optional[str] = None
    ) -> bool:
        """
        更新订单状态
        
        Args:
            order_id: 订单ID
            status: 订单状态
            db: 数据库会话
            transaction_id: 交易ID（可选）
            
        Returns:
            bool: 更新是否成功
        """
        trace_key = request_ctx.get_trace_key()
        
        try:
            # 更新订单状态
            update_stmt = update(MetaOrder).where(
                MetaOrder.id == uuid.UUID(order_id)
            ).values(
                order_status=status,
                updated_at=func.now()
            )
            
            if transaction_id:
                update_stmt = update_stmt.values(
                    transaction_id=transaction_id
                )
            
            await db.execute(update_stmt)
            await db.commit()
            
            return True
            
        except Exception as e:
            await db.rollback()
            logger.error(f"更新订单状态失败: {str(e)}", 
                        exc_info=True, 
                        extra={"request_id": trace_key})
            return False   


    @gate_keeper()
    @log_service_call(method_type="order", tollgate="30-4")
    async def get_user_orders(
        self, 
        user_id: str, 
        db: AsyncSession,
        status: Optional[int] = None,
        page: int = 1,
        page_size: int = 10
    ) -> List[Dict[str, Any]]:
        
        trace_key = request_ctx.get_trace_key()
        
        try:
            # 构建查询条件
            query = select(MetaOrder).where(
                MetaOrder.user_id == uuid.UUID(user_id)
            )
            
            if status is not None:
                query = query.where(MetaOrder.order_status == status)
            
            # 添加分页
            query = query.order_by(MetaOrder.created_at.desc())
            query = query.offset((page - 1) * page_size).limit(page_size)
            
            # 执行查询
            result = await db.execute(query)
            orders = result.scalars().all()
            
            # 格式化订单数据
            order_list = []
            for order in orders:
                order_data = {
                    "order_id": str(order.id),
                    "order_no": order.order_no,
                    "amount": float(order.total_amount),
                    "status": order.order_status,
                    # "product_name": order.product_snapshot.get("name", "未知商品") if order.product_snapshot else "未知商品",
                    "created_at": order.created_at.isoformat() if order.created_at else None
                }
                order_list.append(order_data)
            
            return order_list
            
        except Exception as e:
            logger.error(f"获取用户订单列表失败: {str(e)}", 
                        exc_info=True, 
                        extra={"request_id": trace_key})
            return []