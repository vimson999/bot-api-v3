from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import VARCHAR, Column, Text, ForeignKey, TIMESTAMP, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from .base import Base


class RelPolicyBinding(Base):
    """Policy binding relationship model"""
    __tablename__ = "rel_policy_binding"
    
    policy_id: UUID = Column(PG_UUID, ForeignKey("meta_access_policy.id"), nullable=False)
    target_type: str = Column(VARCHAR(10), nullable=False)
    target_id: UUID = Column(PG_UUID, nullable=False)
    path_id: UUID = Column(PG_UUID, ForeignKey("meta_path.id"), nullable=False)
    
    # Add constraints
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('user','group','app')", 
            name="valid_target_type"
        ),
        CheckConstraint("status IN (0,1,2)", name="valid_status"),
        # Create a unique constraint to prevent duplicate bindings
        UniqueConstraint('policy_id', 'target_type', 'target_id', 'path_id', name='unique_policy_binding')
    )


class RelUserGroup(Base):
    """User-group relationship model"""
    __tablename__ = "rel_user_group"
    
    user_id: UUID = Column(PG_UUID, ForeignKey("meta_user.id"), nullable=False)
    group_id: UUID = Column(PG_UUID, ForeignKey("meta_group.id"), nullable=False)
    joined_at: datetime = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    expired_at: Optional[datetime] = Column(TIMESTAMP(timezone=True), nullable=True)
    
    # Add constraints
    __table_args__ = (
        CheckConstraint("status IN (0,1,2)", name="valid_status"),
        # Create a unique constraint to prevent duplicate memberships
        UniqueConstraint('user_id', 'group_id', name='unique_user_group')
    )
