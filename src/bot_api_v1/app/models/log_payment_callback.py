import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import VARCHAR, Text, TIMESTAMP, func, SmallInteger, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class LogPaymentCallback(Base):
    """
    支付回调记录表
    
    记录支付平台的回调信息和处理状态
    """
    __tablename__ = "log_payment_callback"
    
    # 主键
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键UUID"
    )
    
    # 订单信息
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_order.id"),
        nullable=True,
        comment="订单ID"
    )
    order_no: Mapped[str] = mapped_column(
        VARCHAR(32),
        nullable=False,
        comment="订单编号"
    )
    
    # 支付信息
    payment_channel: Mapped[str] = mapped_column(
        VARCHAR(20),
        nullable=False,
        comment="支付渠道"
    )
    transaction_id: Mapped[Optional[str]] = mapped_column(
        VARCHAR(100),
        nullable=True,
        comment="交易ID"
    )
    
    # 回调数据
    callback_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=func.now(),
        comment="回调时间"
    )
    callback_data: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="回调原始数据，JSON格式"
    )
    callback_result: Mapped[str] = mapped_column(
        VARCHAR(20),
        nullable=False,
        comment="回调结果：SUCCESS/FAIL"
    )
    
    # 处理状态
    handling_status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="处理状态：0-未处理 1-处理中 2-处理成功 3-处理失败"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息"
    )
    
    # 重试信息
    retry_count: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="重试次数"
    )
    next_retry_time: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="下次重试时间"
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
    
    # 关联关系
    order = relationship("MetaOrder", back_populates="payment_callbacks")
    
    def __repr__(self) -> str:
        """支付回调记录的字符串表示"""
        return f"<LogPaymentCallback(id='{self.id}', order_no='{self.order_no}', result='{self.callback_result}')>"