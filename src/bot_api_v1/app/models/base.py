"""
Base model module providing common functionality for all database models.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TypeVar, cast, ClassVar

from sqlalchemy import TIMESTAMP, Column, SmallInteger, Text, event, inspect
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import as_declarative, declared_attr
from sqlalchemy.orm import Query, Session, mapper, Mapped, mapped_column
from sqlalchemy.sql import expression

# Type variable for return type annotations
T = TypeVar('T', bound='Base')


@as_declarative()
class Base:
    """Base class for all SQLAlchemy database models with common functionality."""
    
    # Allow legacy style annotations to work with SQLAlchemy 2.0
    __allow_unmapped__ = True
    
    # Primary key with UUID as default
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Primary key UUID"
    )
    
    # Common metadata fields
    memo: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Additional notes or comments for internal use"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed description visible to users"
    )
    
    # Common system fields
    sort: Mapped[int] = mapped_column(
        SmallInteger,
        default=0,
        nullable=False,
        index=True,
        comment="Sorting order for listing"
    )
    status: Mapped[int] = mapped_column(
        SmallInteger,
        default=1,
        nullable=False,
        index=True,
        comment="Status: 0=disabled, 1=active, 2=pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=expression.text("CURRENT_TIMESTAMP"),
        nullable=False,
        comment="Creation timestamp"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=expression.text("CURRENT_TIMESTAMP"),
        onupdate=expression.text("CURRENT_TIMESTAMP"),
        nullable=False,
        comment="Last update timestamp"
    )
    
    # Automatic tablename generation
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Generate __tablename__ automatically from the class name."""
        return cls.__name__.lower()
    
    def to_dict(self, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Convert model instance to dictionary.
        
        Args:
            exclude: List of field names to exclude from the output
            
        Returns:
            Dictionary representation of the model
        """
        exclude_fields = exclude or []
        result = {}
        
        for key in inspect(self).mapper.column_attrs.keys():
            if key not in exclude_fields:
                value = getattr(self, key)
                # Handle UUID conversion
                if isinstance(value, uuid.UUID):
                    value = str(value)
                # Handle datetime conversion
                elif isinstance(value, datetime):
                    value = value.isoformat()
                
                result[key] = value
                
        return result
    
    @classmethod
    def get_by_id(cls, session: Session, id: uuid.UUID) -> Optional[T]:
        """
        Get an instance by primary key id.
        
        Args:
            session: SQLAlchemy session
            id: UUID primary key
            
        Returns:
            Model instance if found, None otherwise
        """
        return cast(Optional[T], session.query(cls).filter(cls.id == id).first())
    
    @classmethod
    def get_active(cls, session: Session) -> Query:
        """
        Get query for active records (status=1).
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            Query object filtered to active records
        """
        return session.query(cls).filter(cls.status == 1)


# Event listeners for automatic timestamp updates
@event.listens_for(mapper, "before_update")
def _set_updated_at(mapper, connection, target):
    """Automatically update the updated_at field before updates."""
    # Only update if the model has this field
    if hasattr(target, "updated_at"):
        target.updated_at = datetime.now()