import uuid
from datetime import datetime, date # 确保导入 date
from typing import Optional, List, TYPE_CHECKING, Any

from sqlalchemy import (
    String, Text, TIMESTAMP, ForeignKey, CheckConstraint, Index, func,
    BIGINT, INTEGER, SMALLINT, DATE, BOOLEAN
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

# 假设您的 Base 模型在以下路径，如果不同请修改
from .base import Base # 或者 from bot_api_v1.app.models.base import Base

if TYPE_CHECKING:
    # 这个 MetaUser 引用的是您系统中已有的用户表模型
    # 如果您的KOL不直接是系统用户，但您想从KOL角度链接到系统用户（例如KOL也是您平台的注册用户）
    # 那么这个关系定义需要根据实际情况调整。
    # 在当前设计中，MetaKolInfo 是独立于 MetaUser 的。
    pass

class MetaKolInfo(Base):
    __tablename__ = "meta_kol_info"

    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    platform_kol_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    profile_url: Mapped[Optional[str]] = mapped_column(Text)
    nickname: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    cover_url: Mapped[Optional[str]] = mapped_column(Text)
    gender: Mapped[Optional[int]] = mapped_column(SMALLINT, comment="0:未知, 1:男, 2:女")
    region: Mapped[Optional[str]] = mapped_column(String(100))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[Optional[str]] = mapped_column(String(100))
    verified: Mapped[bool] = mapped_column(BOOLEAN, default=False)
    verified_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    initial_follower_count: Mapped[int] = mapped_column(BIGINT, default=0)
    initial_following_count: Mapped[int] = mapped_column(BIGINT, default=0)
    initial_video_count: Mapped[int] = mapped_column(INTEGER, default=0)
    data_last_fetched_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    # 继承自 Base 的字段: id, status, memo, created_at, updated_at, sort

    # 关系: 一个KOL可以有多条视频记录和多条日统计记录
    videos: Mapped[List["MetaVideoInfo"]] = relationship(back_populates="kol_uploader", cascade="all, delete-orphan")
    statistics_daily: Mapped[List["StatisticsKolDaily"]] = relationship(back_populates="kol", cascade="all, delete-orphan")

    __table_args__ = (
        # CheckConstraint("status IN (0, 1, 2)", name="ck_meta_kol_info_status"),
        # CheckConstraint("gender IS NULL OR gender IN (0, 1, 2)", name="ck_meta_kol_info_gender"),
        # Index("idx_meta_kol_info_platform_platform_kol_id", "platform", "platform_kol_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<MetaKolInfo(id={self.id}, platform='{self.platform}', nickname='{self.nickname}')>"


class MetaVideoInfo(Base):
    __tablename__ = "meta_video_info"

    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    platform_video_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content_text: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))

    initial_play_count: Mapped[int] = mapped_column(BIGINT, default=0)
    initial_like_count: Mapped[int] = mapped_column(BIGINT, default=0)
    initial_comment_count: Mapped[int] = mapped_column(BIGINT, default=0)
    initial_share_count: Mapped[int] = mapped_column(BIGINT, default=0)
    initial_collect_count: Mapped[int] = mapped_column(BIGINT, default=0)

    cover_url: Mapped[Optional[str]] = mapped_column(Text)
    video_url: Mapped[Optional[str]] = mapped_column(Text)
    duration_seconds: Mapped[Optional[int]] = mapped_column(INTEGER)
    published_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), index=True)
    
    kol_id: Mapped[Optional[uuid.UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("meta_kol_info.id", ondelete="SET NULL"), index=True)
    data_last_fetched_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    # 继承自 Base 的字段: id, status, memo, created_at, updated_at, sort

    kol_uploader: Mapped["MetaKolInfo"] = relationship(back_populates="videos")
    statistics_daily: Mapped[List["StatisticsVideoDaily"]] = relationship(back_populates="video_info", cascade="all, delete-orphan")

    __table_args__ = (
        # CheckConstraint("status IN (0, 1, 2)", name="ck_meta_video_info_status"),
        # Index("idx_meta_video_info_platform_platform_video_id", "platform", "platform_video_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<MetaVideoInfo(id={self.id}, platform='{self.platform}', platform_video_id='{self.platform_video_id}')>"


class StatisticsVideoDaily(Base):
    __tablename__ = "statistics_video_daily"

    video_info_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("meta_video_info.id", ondelete="CASCADE"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(DATE, nullable=False, index=True) # 使用 date 类型

    play_count: Mapped[int] = mapped_column(BIGINT, default=0)
    like_count: Mapped[int] = mapped_column(BIGINT, default=0)
    comment_count: Mapped[int] = mapped_column(BIGINT, default=0)
    share_count: Mapped[int] = mapped_column(BIGINT, default=0)
    collect_count: Mapped[int] = mapped_column(BIGINT, default=0)

    # 继承自 Base 的字段: id, status, memo, created_at, updated_at, sort
    
    video_info: Mapped["MetaVideoInfo"] = relationship(back_populates="statistics_daily")

    __table_args__ = (
        # CheckConstraint("status IN (0, 1, 2)", name="ck_statistics_video_daily_status"),
        # Index("idx_statistics_video_daily_video_snapshot", "video_info_id", "snapshot_date", unique=True),
    )

    def __repr__(self) -> str:
        return f"<StatisticsVideoDaily(video_info_id={self.video_info_id}, snapshot_date='{self.snapshot_date}')>"


class StatisticsKolDaily(Base):
    __tablename__ = "statistics_kol_daily"

    kol_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("meta_kol_info.id", ondelete="CASCADE"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(DATE, nullable=False, index=True) # 使用 date 类型

    follower_count: Mapped[int] = mapped_column(BIGINT, default=0)
    following_count: Mapped[int] = mapped_column(BIGINT, default=0)
    total_videos_count: Mapped[int] = mapped_column(INTEGER, default=0)
    total_likes_received_on_videos: Mapped[int] = mapped_column(BIGINT, default=0)
    total_comments_received_on_videos: Mapped[int] = mapped_column(BIGINT, default=0)
    total_shares_on_videos: Mapped[int] = mapped_column(BIGINT, default=0)
    total_collections_on_videos: Mapped[int] = mapped_column(BIGINT, default=0)
    total_plays_on_videos: Mapped[int] = mapped_column(BIGINT, default=0)

    # 继承自 Base 的字段: id, status, memo, created_at, updated_at, sort
    
    kol: Mapped["MetaKolInfo"] = relationship(back_populates="statistics_daily")

    __table_args__ = (
        # CheckConstraint("status IN (0, 1, 2)", name="ck_statistics_kol_daily_status"),
        # Index("idx_statistics_kol_daily_kol_snapshot", "kol_id", "snapshot_date", unique=True),
    )

    def __repr__(self) -> str:
        return f"<StatisticsKolDaily(kol_id={self.kol_id}, snapshot_date='{self.snapshot_date}')>"