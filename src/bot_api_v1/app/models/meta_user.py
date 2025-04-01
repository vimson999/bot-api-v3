# src/bot_api_v1/app/models/meta_user.py (更新版)

"""
MetaUser model module for user management across multiple platforms.
"""
import enum
import uuid
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional

from sqlalchemy import CHAR, VARCHAR, Boolean, CheckConstraint, Integer, Text
from sqlalchemy.dialects.postgresql import TEXT, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from bot_api_v1.app.security.crypto.base import decrypt_data, encrypt_data
from .base import Base


class GenderEnum(enum.IntEnum):
    """Gender enumeration for user profiles."""
    UNKNOWN = 0
    MALE = 1
    FEMALE = 2


class PlatformScopeEnum(enum.Enum):
    """Platform scope enumeration."""
    WECHAT = "wx"
    XIAOHONGSHU = "xhs"
    WEB = "web"
    MOBILE = "mobile"


class MetaUser(Base):
    """
    User metadata model representing users across multiple platforms.
    
    This model stores basic user information and platform-specific identifiers
    with proper encryption for sensitive data.
    """
    __tablename__ = "meta_user"
    
    # Allow legacy style annotations (from Base)
    __allow_unmapped__: ClassVar[bool] = True
    
    # Identification fields
    only_id: Mapped[Optional[str]] = mapped_column(
        TEXT, 
        nullable=True,
        index=True,
        comment="Unique identifier within a specific platform"
    )
    unified_id: Mapped[Optional[str]] = mapped_column(
        TEXT, 
        nullable=True, 
        index=True,
        comment="Cross-platform unified identifier"
    )
    
    # Multi-platform information
    scope: Mapped[str] = mapped_column(
        VARCHAR(20), 
        nullable=False,
        index=True,
        comment="Platform scope (wx, xhs, web, mobile)"
    )

    points_account = relationship("MetaUserPoints", back_populates="user", uselist=False)

    # 添加缺失的 points_transactions 关系
    points_transactions = relationship("RelPointsTransaction", back_populates="user")
    # 添加 orders 关系
    orders = relationship("MetaOrder", back_populates="user")

    uni_id: Mapped[Optional[str]] = mapped_column(
        TEXT, 
        nullable=True,
        comment="Platform-specific union ID"
    )
    _open_id: Mapped[Optional[str]] = mapped_column(
        "open_id",
        TEXT, 
        nullable=True,
        comment="Platform-specific open ID"
    )
    
    # Basic information
    nick_name: Mapped[Optional[str]] = mapped_column(
        VARCHAR(100), 
        nullable=True,
        index=True,
        comment="User's nickname or display name"
    )
    gender: Mapped[Optional[int]] = mapped_column(
        Integer,  # 修改为Integer类型，匹配数据库中的smallint类型
        nullable=True,
        comment="User gender: 0=unknown, 1=male, 2=female"
    )
    avatar: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="URL to user's avatar image"
    )
    region_code: Mapped[Optional[str]] = mapped_column(
        CHAR(6), 
        nullable=True,
        comment="Region code (e.g., country or city code)"
    )
    
    # 新增字段 - 微信小程序用户所需
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="User's last login time"
    )
    
    login_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="User's login count"
    )
    
    country: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        comment="User's country"
    )
    
    province: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        comment="User's province"
    )
    
    city: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        comment="User's city"
    )
    
    language: Mapped[Optional[str]] = mapped_column(
        VARCHAR(20),
        nullable=True,
        comment="User's preferred language"
    )
    
    _phone_number: Mapped[Optional[str]] = mapped_column(
        "phone_number",
        VARCHAR(20),
        nullable=True,
        comment="Encrypted user's phone number"
    )
    
    is_authorized: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether the user has authorized to get more information"
    )
    
    auth_time: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Time when user authorized to get information"
    )
    
    last_active_time: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="User's last active time"
    )
    
    wx_app_id: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        comment="WeChat Mini Program ID the user comes from"
    )
    
        # Property for open_id
    @property
    def open_id(self) -> Optional[str]:
        """Get open_id."""
        return self._open_id
    
    @open_id.setter
    def open_id(self, value: Optional[str]) -> None:
        """Set open_id."""
        self._open_id = value
    
    # Property for encrypted phone_number
    @property
    def phone_number(self) -> Optional[str]:
        """Get decrypted phone_number."""
        if self._phone_number is None:
            return None
        return decrypt_data(self._phone_number)
    
    @phone_number.setter
    def phone_number(self, value: Optional[str]) -> None:
        """Set encrypted phone_number."""
        if value is None:
            self._phone_number = None
        else:
            self._phone_number = encrypt_data(value)
    
    # Validators
    @validates('scope')
    def validate_scope(self, key: str, scope: str) -> str:
        """Validate the platform scope value."""
        if scope not in [e.value for e in PlatformScopeEnum]:
            raise ValueError(f"Invalid scope: {scope}")
        return scope
    
    @validates('gender')
    def validate_gender(self, key: str, gender: Optional[int]) -> Optional[int]:
        """Validate the gender value."""
        if gender is not None and gender not in [e.value for e in GenderEnum]:
            raise ValueError(f"Invalid gender: {gender}")
        return gender
    
    # Table constraints and indexes
    __table_args__ = (
        # Constraints
        CheckConstraint(
            "scope IN ('wx','xhs','web','mobile')", 
            name="valid_scope"
        ),
        CheckConstraint(
            "gender IS NULL OR gender IN (0,1,2)",  # 修改为整数类型的检查
            name="valid_gender"
        ),
        CheckConstraint(
            "status IN (0,1,2)", 
            name="valid_status"
        ),
    )
    
    def __repr__(self) -> str:
        """String representation of the user."""
        return f"<User(id='{self.id}', scope='{self.scope}', nickname='{self.nick_name}')>"