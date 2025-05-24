import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import String, TIMESTAMP, CheckConstraint, Index, func, INTEGER, TEXT
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from bot_api_v1.app.models.base import Base

class LogScheduledTaskExecution(Base):
    __tablename__ = "log_scheduled_task_execution"

    # 从Base继承 id, created_at, updated_at (通常Base中不包含status和sort)
    # 如果您的Base模型中包含了status和sort, 并且不适用于此表，可以在这里覆盖它们或不使用它们
    # 此处假设Base类不包含以下所有列，所以我们重新定义

    # id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("uuid_generate_v4()"))
    # created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    # updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    # status: Mapped[int] # 我们将使用自定义的status字段

    execution_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4, index=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, default='scheduled')
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    duration_seconds: Mapped[Optional[int]] = mapped_column(INTEGER)
    
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # 使用字符串类型的状态

    items_to_process: Mapped[Optional[int]] = mapped_column(INTEGER)
    items_succeeded: Mapped[int] = mapped_column(INTEGER, default=0)
    items_failed: Mapped[int] = mapped_column(INTEGER, default=0)
    items_skipped: Mapped[int] = mapped_column(INTEGER, default=0)
    new_items_created: Mapped[int] = mapped_column(INTEGER, default=0)
    items_updated: Mapped[int] = mapped_column(INTEGER, default=0)

    summary_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    hostname: Mapped[Optional[str]] = mapped_column(String(255))
    pid: Mapped[Optional[int]] = mapped_column(INTEGER)

    # 移除了从Base继承的 status 和 sort，因为我们自定义了 status 并不一定需要 sort
    # 如果您的Base模型不包含它们，或者您希望此表有独立的status和sort，则可以取消注释下面的行
    # status: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # 使用字符串类型的状态
    # sort: Mapped[int] = mapped_column(INTEGER, default=0, nullable=False)


    __table_args__ = (
        CheckConstraint(status.in_(['RUNNING', 'COMPLETED_SUCCESS', 'COMPLETED_PARTIAL', 'FAILED', 'CANCELLED']), name="ck_log_scheduled_task_execution_status"),
        # Index("idx_log_scheduled_task_execution_name_start_time", "task_name", func.column("start_time").desc()),
    )

    def __repr__(self) -> str:
        return f"<LogScheduledTaskExecution(id={self.id}, task_name='{self.task_name}', execution_id='{self.execution_id}', status='{self.status}')>"