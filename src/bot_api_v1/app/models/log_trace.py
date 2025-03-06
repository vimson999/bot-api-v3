"""
LogTrace model module for request tracking and logging.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import VARCHAR, CheckConstraint, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LogTrace(Base):
    """
    Log trace model for detailed request logging.
    
    This model captures detailed information about API requests and operations
    for auditing, debugging and monitoring purposes.
    """
    __tablename__ = "log_trace"
    
    # Override Base fields to avoid inheritance
    __table_args__ = (
        CheckConstraint("length(source) > 0", name="valid_source"),
        CheckConstraint("length(method_name) > 0", name="valid_method_name"),
        CheckConstraint(
            "ip_address IS NULL OR "
            "ip_address ~ '^(\\d{1,3}\\.){3}\\d{1,3}$' OR "
            "ip_address ~ '^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$'",
            name="valid_ip_address"
        ),
        CheckConstraint(
            "level IN ('debug', 'info', 'warning', 'error', 'critical')",
            name="valid_level"
        )
    )
    
    # Primary key (override from Base)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key UUID"
    )
    
    # Log trace specific fields
    trace_key: Mapped[str] = mapped_column(
        VARCHAR(36), 
        nullable=False,
        index=True,
        comment="Unique trace key for request tracking"
    )
    source: Mapped[str] = mapped_column(
        VARCHAR(50), 
        nullable=False,
        default="api",
        index=True,
        comment="Source system or component"
    )
    app_id: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50), 
        nullable=True,
        index=True,
        comment="Application identifier"
    )
    user_uuid: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50), 
        nullable=True,
        index=True,
        comment="User UUID if authenticated"
    )
    user_nickname: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50), 
        nullable=True,
        comment="User nickname for readability"
    )
    entity_id: Mapped[Optional[str]] = mapped_column(
        VARCHAR(100), 
        nullable=True,
        comment="Related entity identifier"
    )
    type: Mapped[str] = mapped_column(
        VARCHAR(50), 
        nullable=False,
        default="default",
        comment="Log type classification"
    )
    method_name: Mapped[str] = mapped_column(
        VARCHAR(100), 
        nullable=False,
        comment="Method or endpoint name"
    )
    tollgate: Mapped[Optional[str]] = mapped_column(
        VARCHAR(10), 
        nullable=True,
        comment="Monitoring tollgate identifier"
    )
    level: Mapped[str] = mapped_column(
        VARCHAR(10), 
        nullable=False,
        default="info",
        comment="Log level (debug, info, warning, error, critical)"
    )
    para: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, 
        nullable=True,
        comment="Request parameters as JSON"
    )
    header: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, 
        nullable=True,
        comment="Request headers as JSON"
    )
    body: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="Request body content"
    )
    memo: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="Additional notes"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50), 
        nullable=True,
        comment="Client IP address"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, 
        default=func.now(), 
        nullable=False,
        comment="Log creation timestamp"
    )
    
    def __repr__(self) -> str:
        """String representation of the log trace."""
        return f"<LogTrace(id='{self.id}', trace_key='{self.trace_key}', method='{self.method_name}')>"