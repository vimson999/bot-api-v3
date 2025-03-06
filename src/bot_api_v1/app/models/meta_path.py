from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import VARCHAR, Column, Text, TIMESTAMP, CheckConstraint

from .base import Base


class MetaPath(Base):
    """API path metadata model"""
    __tablename__ = "meta_path"
    
    path_pattern: str = Column(Text, nullable=False)
    name: Optional[str] = Column(Text, nullable=True)
    http_method: Optional[str] = Column(VARCHAR(10), nullable=True)
    
    version: str = Column(VARCHAR(10), default="1.0.0", nullable=False)
    deprecated_at: Optional[datetime] = Column(TIMESTAMP(timezone=True), nullable=True)
    
    auth_type: Optional[str] = Column(VARCHAR(20), nullable=True)
    
    # Add constraints
    __table_args__ = (
        CheckConstraint(
            "http_method IS NULL OR http_method IN ('GET','POST','PUT','DELETE','*')", 
            name="valid_http_method"
        ),
        CheckConstraint(
            "auth_type IS NULL OR auth_type IN ('none','basic','signature')", 
            name="valid_auth_type"
        ),
        CheckConstraint("status IN (0,1,2)", name="valid_status"),
    )
