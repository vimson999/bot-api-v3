import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import VARCHAR, Text, TIMESTAMP, func, SmallInteger
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LogOperation(Base):
    """
    操作日志表
    
    记录系统中各种操作和变更的审计日志
    """
    __tablename__ = "log_operation"
    
    # 主键
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键UUID"
    )
    
    # 操作者信息
    operator_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="操作者ID"
    )
    operator_name: Mapped[Optional[str]] = mapped_column(
        VARCHAR(100),
        nullable=True,
        comment="操作者名称"
    )
    operator_role: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        comment="操作者角色"
    )
    
    # 操作信息
    operation_type: Mapped[str] = mapped_column(
        VARCHAR(50),
        nullable=False,
        comment="操作类型"
    )
    operation_module: Mapped[str] = mapped_column(
        VARCHAR(50),
        nullable=False,
        comment="操作模块"
    )
    operation_content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="操作内容"
    )
    
    # 目标信息
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="目标对象ID"
    )
    target_type: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        comment="目标对象类型"
    )
    
    # 变更前后数据
    before_change: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="变更前数据，JSON格式"
    )
    after_change: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="变更后数据，JSON格式"
    )
    
    # 客户端信息
    ip_address: Mapped[Optional[str]] = mapped_column(
        VARCHAR(50),
        nullable=True,
        comment="IP地址"
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="用户代理信息"
    )
    
    # 状态和错误信息
    status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="操作状态：0-失败 1-成功"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息"
    )
    
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=func.now(),
        comment="创建时间"
    )
    
    def __repr__(self) -> str:
        """操作日志的字符串表示"""
        return f"<LogOperation(id='{self.id}', type='{self.operation_type}', module='{self.operation_module}')>"