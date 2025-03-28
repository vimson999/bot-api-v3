import uuid
from datetime import datetime
from typing import Any, Dict, Optional, List, TYPE_CHECKING

from sqlalchemy import VARCHAR, CheckConstraint, Text, TIMESTAMP, func, SmallInteger, Numeric, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# 使用TYPE_CHECKING解决循环引用问题
if TYPE_CHECKING:
    from .meta_product import MetaProduct
    from .rel_product_package import RelProductPackage
    from .meta_promotion import MetaPromotion
    from .meta_user import MetaUser
    from .log_payment_callback import LogPaymentCallback
    from .rel_points_transaction import RelPointsTransaction


class MetaOrder(Base):
    """
    订单表
    
    记录用户购买商品的订单信息和支付状态
    """
    __tablename__ = "meta_order"
    
    # (保持模型定义不变，但移除最后的relationship定义)
    # 其他字段保持不变...
    
    __table_args__ = (
        CheckConstraint("order_type IN ('POINT', 'PACKAGE', 'SERVICE')", name="valid_order_type"),
        CheckConstraint("original_amount >= 0", name="valid_original_amount"),
        CheckConstraint("discount_amount >= 0", name="valid_discount_amount"),
        CheckConstraint("total_amount >= 0", name="valid_total_amount"),
        CheckConstraint("total_points >= 0", name="valid_total_points"),
        CheckConstraint("order_status IN (0,1,2,3,4,5)", name="valid_order_status"),
        CheckConstraint("payment_channel IS NULL OR payment_channel IN ('WECHAT', 'ALIPAY', 'BANK', 'OTHER')", 
                        name="valid_payment_channel"),
    )
    
    # 主键
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键UUID"
    )
    
    # 订单基本信息
    order_no: Mapped[str] = mapped_column(
        VARCHAR(32),
        nullable=False,
        unique=True,
        comment="订单编号"
    )
    order_type: Mapped[str] = mapped_column(
        VARCHAR(20),
        nullable=False,
        comment="订单类型：POINT-积分 PACKAGE-套餐 SERVICE-服务"
    )
    
    # 用户信息
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_user.id"),
        nullable=False,
        comment="用户ID"
    )
    user_name: Mapped[Optional[str]] = mapped_column(
        VARCHAR(100),
        nullable=True,
        comment="用户名称（冗余）"
    )
    
    # 商品和套餐信息
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_product.id"),
        nullable=True,
        comment="商品ID"
    )
    package_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rel_product_package.id"),
        nullable=True,
        comment="套餐ID"
    )
    promotion_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_promotion.id"),
        nullable=True,
        comment="促销活动ID"
    )
    promotion_code: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        comment="促销代码"
    )
    
    # 价格信息
    original_amount: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="原始金额"
    )
    discount_amount: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
        comment="折扣金额"
    )
    total_amount: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="支付总金额"
    )
    total_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="总积分"
    )
    currency: Mapped[str] = mapped_column(
        VARCHAR(3),
        nullable=False,
        default="CNY",
        comment="货币类型"
    )
    
    # 订单状态
    order_status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="订单状态：0-待支付 1-支付处理中 2-已支付 3-已完成 4-已取消 5-已退款"
    )
    
    # 支付信息
    payment_channel: Mapped[Optional[str]] = mapped_column(
        VARCHAR(20),
        nullable=True,
        comment="支付渠道：WECHAT-微信 ALIPAY-支付宝 BANK-银行 OTHER-其他"
    )
    payment_method: Mapped[Optional[str]] = mapped_column(
        VARCHAR(20),
        nullable=True,
        comment="具体支付方式"
    )
    
    # 微信支付信息
    wx_appid: Mapped[Optional[str]] = mapped_column(
        VARCHAR(255),
        nullable=True,
        comment="微信AppID"
    )
    wx_mchid: Mapped[Optional[str]] = mapped_column(
        VARCHAR(255),
        nullable=True,
        comment="微信商户号"
    )
    wx_transaction_id: Mapped[Optional[str]] = mapped_column(
        VARCHAR(255),
        nullable=True,
        comment="微信交易ID"
    )
    wx_payer_openid: Mapped[Optional[str]] = mapped_column(
        VARCHAR(255),
        nullable=True,
        comment="微信OpenID"
    )
    
    # 其他支付信息
    pay_params: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="支付参数，JSON格式"
    )
    
    # 时间信息
    expired_time: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="支付过期时间"
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="支付时间"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="完成时间"
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="取消时间"
    )
    refunded_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="退款时间"
    )
    
    # 客户端信息
    client_ip: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        comment="客户端IP"
    )
    device_info: Mapped[Optional[str]] = mapped_column(
        VARCHAR(255),
        nullable=True,
        comment="设备信息"
    )
    source_channel: Mapped[Optional[str]] = mapped_column(
        VARCHAR(20),
        nullable=True,
        comment="来源渠道"
    )
    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="订单备注"
    )
    
    # 审计字段
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=func.now(),
        comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=func.now(),
        comment="更新时间"
    )
    
    # 关系将在模型定义后设置