from typing import Optional
from uuid import UUID

from sqlalchemy import VARCHAR, Column, SmallInteger, Text, Integer, CheckConstraint
from sqlalchemy.dialects.postgresql import TEXT

from .base import Base


class MetaApp(Base):
    """Application metadata model"""
    __tablename__ = "meta_app"
    
    name: str = Column(VARCHAR(100), nullable=False, unique=True)
    domain: Optional[str] = Column(TEXT, nullable=True)  # Encrypted field
    
    # Security keys
    public_key: Optional[str] = Column(TEXT, nullable=True)
    private_key: Optional[str] = Column(TEXT, nullable=True)
    key_version: int = Column(SmallInteger, default=1, nullable=False)
    sign_type: Optional[str] = Column(TEXT, nullable=True)
    sign_config: Optional[str] = Column(TEXT, nullable=True)
    
    # Configuration
    callback_config: Optional[str] = Column(TEXT, nullable=True)
    ip_whitelist: Optional[str] = Column(TEXT, nullable=True)
    rate_limit: int = Column(Integer, default=1000, nullable=False)
    
    # Add constraints
    __table_args__ = (
        CheckConstraint("status IN (0,1,2)", name="valid_status"),
    )
