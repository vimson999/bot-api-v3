import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, TIMESTAMP, func, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class MetaUserPoints(Base):
    """
    用户积分账户表
    
    管理用户的积分余额、冻结积分和使用记录
    """
    __tablename__ = "meta_user_points"
    
    __table_args__ = (
        CheckConstraint("total_points >= 0", name="check_total_points_positive"),
        CheckConstraint("available_points >= 0", name="check_available_points_positive"),
        CheckConstraint("frozen_points >= 0", name="check_frozen_points_positive"),
        CheckConstraint("used_points >= 0", name="check_used_points_positive"),
        CheckConstraint("expired_points >= 0", name="check_expired_points_positive"),
    )
    
    # 主键
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键UUID"
    )
    
    # 用户信息
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meta_user.id"),
        nullable=False,
        unique=True,
        comment="用户ID"
    )
    
    # 积分信息
    total_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="总积分"
    )
    available_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="可用积分"
    )
    frozen_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="冻结积分"
    )
    used_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="已使用积分"
    )
    expired_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="已过期积分"
    )
    
    # 最近操作时间
    last_consume_time: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="最近消费时间"
    )
    last_earn_time: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="最近获取时间"
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
    user = relationship("MetaUser", back_populates="points_account")
    transactions = relationship("RelPointsTransaction", back_populates="account")
    
    def __repr__(self) -> str:
        """用户积分账户的字符串表示"""
        return f"<MetaUserPoints(id='{self.id}', user_id='{self.user_id}', available='{self.available_points}')>"