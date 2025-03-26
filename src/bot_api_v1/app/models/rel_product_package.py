import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import VARCHAR, CheckConstraint, Text, TIMESTAMP, func, SmallInteger, Numeric, Boolean, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class RelProductPackage(Base):
    """
    积分套餐表
    
    管理积分套餐产品及其相关信息
    """
    __tablename__ = "rel_product_package"
    
    __table_args__ = (
        CheckConstraint("package_price > 0", name="valid_package_price"),
        CheckConstraint("total_points > 0", name="valid_total_points"),
        CheckConstraint("status IN (0,1,2)", name="valid_status"),
    )
    
    # 主键
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键UUID"
    )
    
    # 套餐基本信息
    name: Mapped[str] = mapped_column(
        VARCHAR(100),
        nullable=False,
        comment="套餐名称"
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_product.id"),
        nullable=False,
        comment="关联产品ID"
    )
    promotion_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_promotion.id"),
        nullable=True,
        comment="关联促销活动ID"
    )
    
    # 套餐价格和积分
    package_price: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="套餐价格"
    )
    total_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="套餐包含总积分"
    )
    discount_rate: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="套餐折扣率"
    )
    
    # 展示和推荐信息
    is_hot: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否热门套餐"
    )
    is_recommended: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否推荐套餐"
    )
    sort: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="排序序号"
    )
    
    # 有效期和状态
    expire_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default="2099-12-31 23:59:59+08",
        comment="过期时间"
    )
    status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="状态：0-下架 1-上架 2-售罄"
    )
    
    # 描述和内容
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="套餐描述"
    )
    cover_image: Mapped[Optional[str]] = mapped_column(
        VARCHAR(255),
        nullable=True,
        comment="套餐封面图URL"
    )
    detail_content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="套餐详情内容"
    )
    tags: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="套餐标签，JSON格式"
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
    product = relationship("MetaProduct", back_populates="packages")
    promotion = relationship("MetaPromotion", back_populates="packages")
    orders = relationship("MetaOrder", back_populates="package")
    points_transactions = relationship("RelPointsTransaction", back_populates="package")
    
    def __repr__(self) -> str:
        """套餐的字符串表示"""
        return f"<RelProductPackage(id='{self.id}', name='{self.name}', price='{self.package_price}')>"