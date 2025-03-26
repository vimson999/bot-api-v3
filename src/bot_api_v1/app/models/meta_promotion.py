import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import VARCHAR, CheckConstraint, Text, TIMESTAMP, func, SmallInteger, Numeric, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class MetaPromotion(Base):
    """
    营销活动表
    
    管理各类促销活动，包括折扣、满减、赠品等
    """
    __tablename__ = "meta_promotion"
    
    __table_args__ = (
        CheckConstraint("promo_type IN ('DISCOUNT', 'AMOUNT_OFF', 'GIFT', 'SPECIAL')", name="valid_promo_type"),
        CheckConstraint("status IN (0,1,2)", name="valid_status"),
    )
    
    # 主键
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键UUID"
    )
    
    # 促销基本信息
    name: Mapped[str] = mapped_column(
        VARCHAR(100),
        nullable=False,
        comment="促销活动名称"
    )
    promo_code: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        unique=True,
        comment="促销代码"
    )
    promo_type: Mapped[str] = mapped_column(
        VARCHAR(20),
        nullable=False,
        comment="促销类型：DISCOUNT-折扣 AMOUNT_OFF-满减 GIFT-赠品 SPECIAL-特殊"
    )
    
    # 促销规则参数
    discount_rate: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="折扣比例"
    )
    min_purchase_amount: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="最低购买金额"
    )
    amount_off: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="满减金额"
    )
    bonus_points: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="赠送积分"
    )
    
    # 有效期和适用范围
    start_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        comment="开始时间"
    )
    end_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        comment="结束时间"
    )
    applicable_products: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="适用产品IDs，JSON格式"
    )
    applicable_user_tags: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="适用用户标签，JSON格式"
    )
    
    # 使用限制
    usage_limit_per_user: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="每用户使用次数限制"
    )
    total_usage_limit: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="总使用次数限制"
    )
    current_usage_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="当前已使用次数"
    )
    
    # 状态和优先级
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="优先级，处理多促销冲突"
    )
    status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="状态：0-未激活 1-进行中 2-已结束"
    )
    memo: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )
    
    # 审计字段
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="创建人UUID"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=func.now(),
        comment="创建时间"
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="更新人UUID"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=func.now(),
        comment="更新时间"
    )
    
    # 关联关系
    packages = relationship("RelProductPackage", back_populates="promotion")
    orders = relationship("MetaOrder", back_populates="promotion")
    
    def __repr__(self) -> str:
        """促销活动的字符串表示"""
        return f"<MetaPromotion(id='{self.id}', name='{self.name}', type='{self.promo_type}')>"