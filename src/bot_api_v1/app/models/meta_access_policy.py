from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import VARCHAR, Column, SmallInteger, TIMESTAMP, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base


class MetaAccessPolicy(Base):
    """Access policy metadata model"""
    __tablename__ = "meta_access_policy"
    
    name: str = Column(VARCHAR(100), nullable=False)
    
    effect: Optional[str] = Column(VARCHAR(10), nullable=True)
    conditions: Optional[Dict[str, Any]] = Column(JSONB, nullable=True)
    
    valid_from: Optional[datetime] = Column(TIMESTAMP(timezone=True), nullable=True)
    valid_until: Optional[datetime] = Column(TIMESTAMP(timezone=True), nullable=True)
    
    priority: int = Column(SmallInteger, default=1, nullable=False)
    
    # Add constraints
    __table_args__ = (
        CheckConstraint(
            "effect IS NULL OR effect IN ('allow','deny')", 
            name="valid_effect"
        ),
        CheckConstraint("status IN (0,1,2)", name="valid_status"),
    )
