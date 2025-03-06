from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import VARCHAR, Column, Text, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from .base import Base


class MetaGroup(Base):
    """User group metadata model"""
    __tablename__ = "meta_group"
    
    app_id: UUID = Column(PG_UUID, ForeignKey("meta_app.id"), nullable=False)
    scope: str = Column(VARCHAR(20), nullable=False)
    name: str = Column(VARCHAR(100), nullable=False)
    
    level_type: Optional[str] = Column(VARCHAR(20), nullable=True)
    upgrade_rules: Optional[Dict[str, Any]] = Column(JSONB, nullable=True)
    capacity_rules: Optional[Dict[str, Any]] = Column(JSONB, nullable=True)
    
    icon: Optional[str] = Column(Text, nullable=True)
    
    # Add constraints
    __table_args__ = (
        CheckConstraint("scope IN ('wx','xhs','web','mobile')", name="valid_scope"),
        CheckConstraint(
            "level_type IS NULL OR level_type IN ('vip','payment','credit')", 
            name="valid_level_type"
        ),
        CheckConstraint("status IN (0,1,2)", name="valid_status"),
    )
