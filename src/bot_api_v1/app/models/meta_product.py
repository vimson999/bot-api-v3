import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import VARCHAR, CheckConstraint, Text, TIMESTAMP, func, SmallInteger, Numeric, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class MetaProduct(Base):
    """
    商品基础信息表
    
    保存商品的基本信息，包括价格、类型和库存等
    """
    __tablename__ = "meta_product"
    
    __table_args__ = (
        CheckConstraint("product_type IN ('POINT', 'PACKAGE', 'SERVICE')", name="valid_product_type"),
        CheckConstraint("currency IN ('CNY','USD','EUR')", name="valid_currency"),
        CheckConstraint("status IN (0,1,2)", name="valid_status"),
    )
    
    # 主键
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键UUID"
    )
    
    # 商品基本信息
    name: Mapped[str] = mapped_column(
        VARCHAR(100),
        nullable=False,
        comment="商品名称"
    )
    sku_code: Mapped[str] = mapped_column(
        VARCHAR(50),
        nullable=False,
        unique=True,
        comment="商品SKU编码"
    )
    product_type: Mapped[str] = mapped_column(
        VARCHAR(20),
        nullable=False,
        comment="商品类型：POINT-积分 PACKAGE-套餐 SERVICE-服务"
    )
    point_amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="积分数量"
    )
    original_price: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="原始价格"
    )
    sale_price: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="销售价格"
    )
    currency: Mapped[str] = mapped_column(
        VARCHAR(3),
        nullable=False,
        default="CNY",
        comment="货币类型：CNY-人民币 USD-美元 EUR-欧元"
    )
    
    # 商品图片和详情
    cover_image: Mapped[Optional[str]] = mapped_column(
        VARCHAR(255),
        nullable=True,
        comment="商品封面图URL"
    )
    image_list: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="商品图片列表，JSON格式"
    )
    detail_content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="富文本详情内容"
    )
    
    # 有效期和库存
    expire_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=365,
        comment="购买后有效期（天）"
    )
    expire_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default="2099-12-31 23:59:59+08",
        comment="过期时间"
    )
    inventory_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=-1,
        comment="库存数量，-1表示不限库存"
    )
    
    # 状态和分类信息
    status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="商品状态：0-下架 1-上架 2-售罄"
    )
    has_promotion: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否有促销活动"
    )
    sort: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="排序序号"
    )
    tags: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="商品标签，JSON格式"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="商品描述"
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
    packages = relationship("RelProductPackage", back_populates="product")
    orders = relationship("MetaOrder", back_populates="product")
    points_transactions = relationship("RelPointsTransaction", back_populates="product")
    
    def __repr__(self) -> str:
        """商品信息的字符串表示"""
        return f"<MetaProduct(id='{self.id}', name='{self.name}', type='{self.product_type}')>"