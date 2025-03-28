import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import VARCHAR, Text, TIMESTAMP, func, SmallInteger, Integer, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class RelPointsTransaction(Base):
    """
    积分记录表
    
    记录用户积分的变动明细和交易记录
    """
    __tablename__ = "rel_points_transaction"
    
    __table_args__ = (
        CheckConstraint("remaining_points >= 0", name="check_remaining_points_positive"),
        CheckConstraint(
            "transaction_type IN ('PURCHASE', 'CONSUME', 'EXPIRE', 'ADJUST', 'REFUND')",
            name="valid_transaction_type"
        ),
        CheckConstraint("transaction_status IN (0, 1, 2)", name="valid_transaction_status"),
    )
    
    # 主键
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键UUID"
    )
    
    # 交易基本信息
    transaction_no: Mapped[str] = mapped_column(
        VARCHAR(32),
        nullable=False,
        unique=True,
        comment="交易编号"
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_user.id"),
        nullable=False,
        comment="用户ID"
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_user_points.id"),
        nullable=False,
        comment="账户ID"
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_order.id"),
        nullable=True,
        comment="订单ID"
    )
    
    # 积分变动信息
    points_change: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="积分变动量，正数表示增加，负数表示消费"
    )
    remaining_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="剩余积分"
    )
    
    # 交易类型和状态
    transaction_type: Mapped[str] = mapped_column(
        VARCHAR(20),
        nullable=False,
        comment="交易类型：PURCHASE-购买 CONSUME-消费 EXPIRE-过期 ADJUST-调整 REFUND-退款"
    )
    transaction_status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="交易状态：0-失败 1-成功 2-处理中"
    )
    
    # 关联信息
    related_product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_product.id"),
        nullable=True,
        comment="相关商品ID"
    )
    related_package_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rel_product_package.id"),
        nullable=True,
        comment="相关套餐ID"
    )
    related_api_key_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_auth_key.id"),
        nullable=True,
        comment="相关API密钥ID"
    )
    
    # API使用信息
    api_name: Mapped[Optional[str]] = mapped_column(
        VARCHAR(100),
        nullable=True,
        comment="API名称"
    )
    api_path: Mapped[Optional[str]] = mapped_column(
        VARCHAR(255),
        nullable=True,
        comment="API路径"
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        comment="API请求ID"
    )
    
    # 有效期和备注
    expire_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default="2099-12-31 23:59:59+08",
        comment="过期时间"
    )
    balance_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="交易时账户余额快照，JSON格式"
    )
    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )
    
    # 客户端信息
    client_ip: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        comment="客户端IP"
    )
    
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=func.now(),
        comment="创建时间"
    )
    
    from .meta_order import MetaOrder


    # 关联关系
    user = relationship("MetaUser", back_populates="points_transactions")
    account = relationship("MetaUserPoints", back_populates="transactions")
    order = relationship("MetaOrder", back_populates="points_transactions")
    # order = relationship("MetaOrder", back_populates="transactions")


    product = relationship("MetaProduct", back_populates="points_transactions")
    package = relationship("RelProductPackage", back_populates="points_transactions")
    api_key = relationship("MetaAuthKey", back_populates="points_transactions")
    
    def __repr__(self) -> str:
        """积分交易记录的字符串表示"""
        return f"<RelPointsTransaction(id='{self.id}', transaction_no='{self.transaction_no}', points_change='{self.points_change}')>"