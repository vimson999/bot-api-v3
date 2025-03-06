# bot_api_v1/app/db/base.py

from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy import Column, Integer, DateTime, func, text, String
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.sql.expression import or_
import uuid
from typing import Dict, Any, List, Optional, TypeVar, Type, Generic
import re

Base = declarative_base()

class BaseModel(Base):
    """为所有模型提供基础字段的抽象基类"""
    __abstract__ = True

    @declared_attr
    def __tablename__(cls) -> str:
        """自动生成表名"""
        # 将驼峰命名转换为下划线命名
        return re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.current_timestamp(), nullable=False, index=True)
    updated_at = Column(
        TIMESTAMP(timezone=True), 
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False
    )
    status = Column(Integer, default=1, nullable=False, index=True)
    sort = Column(Integer, default=0, nullable=False)

    @classmethod
    async def get_active(cls, session, **kwargs):
        """获取活跃状态的记录"""
        return await session.execute(
            select(cls).where(
                cls.status == 1,
                *[getattr(cls, k) == v for k, v in kwargs.items()]
            )
        )
    
    @classmethod
    def soft_delete_filter(cls):
        """软删除过滤条件"""
        return cls.status != 0
        
    def dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
