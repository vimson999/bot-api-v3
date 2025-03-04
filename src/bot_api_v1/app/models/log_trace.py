
# bot_api_v1/app/models/log_trace.py
from sqlalchemy import Column, String, Text, DateTime, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID
import uuid
from datetime import datetime
from bot_api_v1.app.db.base import Base

class LogTrace(Base):
    __tablename__ = "log_trace"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_key = Column(String(36), index=True, nullable=False)
    source = Column(String(50), index=True)
    app_id = Column(String(50), nullable=True, index=True)
    user_id = Column(String(50), nullable=True, index=True)
    uni_id = Column(String(50), nullable=True, index=True)
    entity_id = Column(String(100), nullable=True, index=True)
    type = Column(String(50), index=True)
    method_name = Column(String(100), index=True)
    tollgate = Column(String(10))
    level = Column(String(10), index=True)
    # 使用PostgreSQL的JSONB类型
    para = Column(JSONB, nullable=True)  
    header = Column(JSONB, nullable=True)  
    body = Column(Text, nullable=True)
    memo = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.now, index=True)