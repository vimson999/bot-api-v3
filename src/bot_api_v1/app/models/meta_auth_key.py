from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from sqlalchemy import Column, String, Integer, CheckConstraint, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, TIMESTAMP
from .base import Base

class MetaAuthKey(Base):
    """API授权密钥模型"""
    __tablename__ = "meta_auth_key"
    
    # 密钥相关
    key_value = Column(String(100), nullable=False, unique=True, index=True)
    key_name = Column(String(100), nullable=False)
    key_status = Column(Integer, default=1, nullable=False, index=True)
    
    # 关联信息（无外键约束）
    app_id = Column(PG_UUID, nullable=True, index=True)
    user_id = Column(PG_UUID, nullable=True, index=True)
    creator_id = Column(PG_UUID, nullable=True)
    activator_id = Column(PG_UUID, nullable=True)
    deactivator_id = Column(PG_UUID, nullable=True)
    
    # 使用范围与限制
    scope = Column(String(255), nullable=True)
    rate_limit = Column(Integer, default=100)
    call_limit = Column(Integer, default=10000)
    call_count = Column(Integer, default=0)
    
    # 时间相关
    activated_at = Column(TIMESTAMP(timezone=True), nullable=True)
    expired_at = Column(TIMESTAMP(timezone=True), nullable=True, index=True)
    deactivated_at = Column(TIMESTAMP(timezone=True), nullable=True)
    
    # 附加信息
    purchase_record_id = Column(PG_UUID, nullable=True)
    note = Column(Text, nullable=True)
    
    # 映射到数据库中的'metadata'列
    key_metadata = Column("metadata", JSONB, nullable=True)
    
    # 表约束
    __table_args__ = (
        CheckConstraint("key_status IN (0,1,2,3)", name="valid_key_status"),
        CheckConstraint("status IN (0,1,2)", name="valid_status"),
    )
    
    def is_valid(self) -> bool:
        """检查密钥是否有效"""
        now = datetime.now()
        # 密钥状态必须为激活(1)，且通用状态不为禁用(0)
        status_valid = (self.key_status == 1 and self.status != 0)
        # 检查是否在有效期内
        time_valid = (self.expired_at is None or now < self.expired_at)
        # 检查调用次数是否超限
        count_valid = (self.call_limit == 0 or self.call_count < self.call_limit)
        
        return status_valid and time_valid and count_valid