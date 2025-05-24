# src/bot_api_v1/app/services/business/media_data_service.py (或者一个新文件)

import uuid
import json
import os # 用于获取hostname和pid
import platform as pf # 用于获取hostname
from datetime import date, datetime # 确保导入 datetime
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session # 用于同步会话的类型提示
from sqlalchemy import select, exc as sqlalchemy_exc # 导入 select 和 sqlalchemy 异常
from sqlalchemy import select, update, and_, desc, func, text,create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from sqlalchemy.orm import joinedload,Session

from bot_api_v1.app.models.log_task_execution import LogScheduledTaskExecution
from bot_api_v1.app.models.meta_info import MetaVideoInfo, MetaKolInfo, StatisticsVideoDaily, StatisticsKolDaily # 假设新模型放在这里
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.db.session import get_sync_db_session
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
from bot_api_v1.app.models.meta_user_points import MetaUserPoints
from bot_api_v1.app.models.rel_points_transaction import RelPointsTransaction
from bot_api_v1.app.models.meta_user import MetaUser
from bot_api_v1.app.services.business.user_cache_service import UserCacheService
from bot_api_v1.app.services.business.user_service import UserService

class MediaDataService:
    async def get_kol_by_platform_id(self, db: AsyncSession, platform: str, platform_kol_id: str) -> Optional[MetaKolInfo]:
        """
        [异步辅助方法] 根据平台和平台特定ID获取KOL信息。
        """
        if not platform or not platform_kol_id:
            return None
        try:
            stmt = select(MetaKolInfo).where(
                MetaKolInfo.platform == platform,
                MetaKolInfo.platform_kol_id == platform_kol_id
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"查询KOL失败 (platform: {platform}, platform_kol_id: {platform_kol_id}): {e}", exc_info=True)
            return None

    async def create_or_update_kol_info(self, db: AsyncSession, kol_data: Dict[str, Any]) -> Optional[MetaKolInfo]:
        """
        [异步] 创建或更新KOL信息。
        如果KOL已存在（基于platform和platform_kol_id），则更新其信息。
        否则，创建新的KOL记录。

        Args:
            db: SQLAlchemy 异步会话。
            kol_data: 包含KOL信息的字典。必需字段: 'platform', 'platform_kol_id'。
                      可选字段: 'profile_url', 'nickname', 'bio', 'avatar_url',
                               'cover_url', 'gender', 'region', 'city', 'country',
                               'verified', 'verified_reason', 'initial_follower_count',
                               'initial_following_count', 'initial_video_count', 'status', 'memo'.
        Returns:
            MetaKolInfo 对象或 None (如果操作失败)。
        """
        platform = kol_data.get("platform")
        platform_kol_id = kol_data.get("platform_kol_id")

        if not platform or not platform_kol_id:
            logger.error("创建/更新KOL失败：platform 和 platform_kol_id 是必需的。")
            return None

        try:
            existing_kol = await self.get_kol_by_platform_id(db, platform, platform_kol_id)
            now = datetime.now()

            if existing_kol:
                logger.info(f"找到已存在的KOL: {platform} - {platform_kol_id}，进行更新。")
                updated_fields_count = 0
                for key, value in kol_data.items():
                    if hasattr(existing_kol, key) and getattr(existing_kol, key) != value:
                        setattr(existing_kol, key, value)
                        updated_fields_count +=1
                        logger.debug(f"更新KOL字段 {key} 为 {value}")
                
                if updated_fields_count > 0 or not existing_kol.data_last_fetched_at: # 如果有字段更新或从未设置过此时间
                    existing_kol.data_last_fetched_at = now
                # existing_kol.updated_at 会由Base模型自动处理或SQL触发器

                kol_to_return = existing_kol
            else:
                logger.info(f"未找到KOL: {platform} - {platform_kol_id}，创建新的记录。")
                # 准备创建所需的数据，过滤掉不在模型中的键
                valid_keys = {column.name for column in MetaKolInfo.__table__.columns}
                kol_data_for_create = {k: v for k, v in kol_data.items() if k in valid_keys}
                
                # 确保核心字段存在
                kol_data_for_create['platform'] = platform
                kol_data_for_create['platform_kol_id'] = platform_kol_id
                kol_data_for_create['data_last_fetched_at'] = now

                new_kol = MetaKolInfo(**kol_data_for_create)
                db.add(new_kol)
                kol_to_return = new_kol
            
            await db.commit()
            await db.refresh(kol_to_return)
            return kol_to_return
        except sqlalchemy_exc.IntegrityError as e: # 捕获唯一约束冲突等
            await db.rollback()
            logger.error(f"创建/更新KOL时发生数据库完整性错误 ({platform} - {platform_kol_id}): {e}")
            # 尝试再次获取，以防并发创建导致此错误
            return await self.get_kol_by_platform_id(db, platform, platform_kol_id)
        except Exception as e:
            await db.rollback()
            logger.error(f"创建/更新KOL时发生未知错误 ({platform} - {platform_kol_id}): {e}", exc_info=True)
            return None

    async def get_video_by_platform_id(self, db: AsyncSession, platform: str, platform_video_id: str) -> Optional[MetaVideoInfo]:
        """
        [异步辅助方法] 根据平台和平台特定视频ID获取视频信息。
        """
        if not platform or not platform_video_id:
            return None
        try:
            stmt = select(MetaVideoInfo).where(
                MetaVideoInfo.platform == platform,
                MetaVideoInfo.platform_video_id == platform_video_id
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"查询视频失败 (platform: {platform}, platform_video_id: {platform_video_id}): {e}", exc_info=True)
            return None

    async def create_or_update_video_info(self, db: AsyncSession, video_data: Dict[str, Any], kol_id: uuid.UUID) -> Optional[MetaVideoInfo]:
        """
        [异步] 创建或更新视频元数据记录。
        如果视频已存在（基于platform和platform_video_id），则更新其信息。

        Args:
            db: SQLAlchemy 异步会话。
            video_data: 包含视频信息的字典。必需字段: 'platform', 'platform_video_id', 'original_url'.
                        可选字段对应 MetaVideoInfo 模型。
            kol_id: 关联的 MetaKolInfo 的主键 (UUID)。

        Returns:
            MetaVideoInfo 对象或 None。
        """
        platform = video_data.get("platform")
        platform_video_id = video_data.get("platform_video_id")
        original_url = video_data.get("original_url")

        if not platform or not platform_video_id or not original_url:
            logger.error("创建/更新视频失败：platform, platform_video_id, 和 original_url 是必需的。")
            return None
        if not kol_id: # 确保kol_id有效
            logger.error(f"创建/更新视频失败 ({platform} - {platform_video_id}): kol_id 不能为空。")
            return None

        try:
            existing_video = await self.get_video_by_platform_id(db, platform, platform_video_id)
            now = datetime.now()

            if existing_video:
                logger.info(f"找到已存在的视频: {platform} - {platform_video_id}，准备更新。")
                updated_fields_count = 0
                for key, value in video_data.items():
                    if hasattr(existing_video, key) and getattr(existing_video, key) != value:
                        # 特殊处理 tags，确保是列表
                        if key == "tags" and value is not None and not isinstance(value, list):
                            try:
                                # 尝试将字符串（如JSON字符串数组）解析为列表
                                parsed_value = json.loads(value)
                                if isinstance(parsed_value, list):
                                    value = parsed_value
                                else: # 如果解析后不是列表，则作为单元素列表
                                    value = [str(value)]
                            except: # 解析失败，则作为单元素列表
                                value = [str(value)]
                        elif key == "tags" and value is None:
                            value = [] # 如果传入None，则视为空列表

                        setattr(existing_video, key, value)
                        updated_fields_count +=1
                        logger.debug(f"更新视频字段 {key}")
                
                # 确保 kol_id 也被正确更新（如果传入的 video_data 中包含它，或者作为独立参数）
                if existing_video.kol_id != kol_id:
                    existing_video.kol_id = kol_id
                    updated_fields_count +=1
                    logger.debug(f"更新视频的 kol_id 为 {kol_id}")

                if updated_fields_count > 0 or not existing_video.data_last_fetched_at:
                    existing_video.data_last_fetched_at = now
                # existing_video.updated_at 会由Base模型自动处理

                video_to_return = existing_video
            else:
                logger.info(f"未找到视频: {platform} - {platform_video_id}，创建新的记录。")
                valid_keys = {column.name for column in MetaVideoInfo.__table__.columns}
                video_data_for_create = {k: v for k, v in video_data.items() if k in valid_keys}

                # 确保核心字段
                video_data_for_create['platform'] = platform
                video_data_for_create['platform_video_id'] = platform_video_id
                video_data_for_create['original_url'] = original_url
                video_data_for_create['kol_id'] = kol_id
                video_data_for_create['data_last_fetched_at'] = now
                
                # 特殊处理 tags
                tags_value = video_data.get("tags")
                if tags_value is not None and not isinstance(tags_value, list):
                    try:
                        parsed_tags = json.loads(tags_value)
                        video_data_for_create['tags'] = parsed_tags if isinstance(parsed_tags, list) else [str(tags_value)]
                    except:
                         video_data_for_create['tags'] = [str(tags_value)]
                elif tags_value is None:
                    video_data_for_create['tags'] = []


                new_video = MetaVideoInfo(**video_data_for_create)
                db.add(new_video)
                video_to_return = new_video
            
            await db.commit()
            await db.refresh(video_to_return)
            return video_to_return
        except sqlalchemy_exc.IntegrityError as e:
            await db.rollback()
            logger.error(f"创建/更新视频时发生数据库完整性错误 ({platform} - {platform_video_id}): {e}")
            return await self.get_video_by_platform_id(db, platform, platform_video_id)
        except Exception as e:
            await db.rollback()
            logger.error(f"创建/更新视频时发生未知错误 ({platform} - {platform_video_id}): {e}", exc_info=True)
            return None

    async def add_daily_video_stats(self, db: AsyncSession, video_info_id: uuid.UUID, snapshot_date: date, stats_data: Dict[str, Any]) -> Optional[StatisticsVideoDaily]:
        """
        [异步] 为指定视频添加或更新一条新的日统计记录。
        如果当天的记录已存在，则更新它；否则，创建新记录。
        """
        if not video_info_id or not snapshot_date or not stats_data:
            logger.error("添加视频日统计失败：video_info_id, snapshot_date, 和 stats_data 不能为空。")
            return None
        
        try:
            # 检查当天是否已存在统计记录
            stmt = select(StatisticsVideoDaily).where(
                StatisticsVideoDaily.video_info_id == video_info_id,
                StatisticsVideoDaily.snapshot_date == snapshot_date
            )
            result = await db.execute(stmt)
            existing_stat = result.scalar_one_or_none()

            stat_to_return: Optional[StatisticsVideoDaily] = None

            if existing_stat:
                logger.info(f"视频日统计记录已存在 ({video_info_id} on {snapshot_date})，进行更新。")
                updated_fields_count = 0
                for key, value in stats_data.items():
                    if hasattr(existing_stat, key) and getattr(existing_stat, key) != value:
                        setattr(existing_stat, key, value)
                        updated_fields_count += 1
                        logger.debug(f"更新视频统计字段 {key} 为 {value}")
                # 如果有更新，Base模型会自动处理updated_at
                stat_to_return = existing_stat
            else:
                logger.info(f"创建新的视频日统计记录 ({video_info_id} on {snapshot_date})。")
                daily_stat_data = {
                    "video_info_id": video_info_id,
                    "snapshot_date": snapshot_date,
                    **stats_data  # 解包传入的统计数据
                }
                # 确保所有 StatisticsVideoDaily 的字段都被正确填充，或有默认值
                new_stat = StatisticsVideoDaily(**daily_stat_data)
                db.add(new_stat)
                stat_to_return = new_stat
            
            await db.commit()
            if stat_to_return: # 确保对象在会话中且未被回滚
                await db.refresh(stat_to_return)
            return stat_to_return
        except Exception as e:
            await db.rollback()
            logger.error(f"添加或更新视频日统计时发生错误 ({video_info_id} on {snapshot_date}): {e}", exc_info=True)
            return None

    async def add_daily_kol_stats(self, db: AsyncSession, kol_id: uuid.UUID, snapshot_date: date, stats_data: Dict[str, Any]) -> Optional[StatisticsKolDaily]:
        """
        [异步] 为指定KOL添加或更新一条新的日统计记录。
        如果当天的记录已存在，则更新它；否则，创建新记录。
        """
        if not kol_id or not snapshot_date or not stats_data:
            logger.error("添加KOL日统计失败：kol_id, snapshot_date, 和 stats_data 不能为空。")
            return None
        
        try:
            # 检查当天是否已存在统计记录
            stmt = select(StatisticsKolDaily).where(
                StatisticsKolDaily.kol_id == kol_id,
                StatisticsKolDaily.snapshot_date == snapshot_date
            )
            result = await db.execute(stmt)
            existing_stat = result.scalar_one_or_none()

            stat_to_return: Optional[StatisticsKolDaily] = None

            if existing_stat:
                logger.info(f"KOL日统计记录已存在 ({kol_id} on {snapshot_date})，进行更新。")
                updated_fields_count = 0
                for key, value in stats_data.items():
                    if hasattr(existing_stat, key) and getattr(existing_stat, key) != value:
                        setattr(existing_stat, key, value)
                        updated_fields_count += 1
                        logger.debug(f"更新KOL统计字段 {key} 为 {value}")
                stat_to_return = existing_stat
            else:
                logger.info(f"创建新的KOL日统计记录 ({kol_id} on {snapshot_date})。")
                daily_stat_data = {
                    "kol_id": kol_id,
                    "snapshot_date": snapshot_date,
                    **stats_data
                }
                new_stat = StatisticsKolDaily(**daily_stat_data)
                db.add(new_stat)
                stat_to_return = new_stat
            
            await db.commit()
            if stat_to_return:
                 await db.refresh(stat_to_return)
            return stat_to_return
        except Exception as e:
            await db.rollback()
            logger.error(f"添加或更新KOL日统计时发生错误 ({kol_id} on {snapshot_date}): {e}", exc_info=True)
            return None

    

    def get_or_create_kol_info_sync(self, db_session: Session, kol_platform_data: Dict[str, Any]) -> Optional[MetaKolInfo]:
        """
        [同步] 获取或创建KOL信息。
        如果KOL已存在（基于platform和platform_kol_id），则更新其信息。
        否则，创建新的KOL记录。

        Args:
            db_session: SQLAlchemy 同步会话。
            kol_platform_data: 包含KOL信息的字典，至少需要 platform 和 platform_kol_id。
                               其他可选字段如 nickname, avatar_url, bio, profile_url 等。
        Returns:
            MetaKolInfo 对象或 None (如果操作失败)。
        """
        platform = kol_platform_data.get("platform")
        platform_kol_id = kol_platform_data.get("platform_kol_id")

        if not platform or not platform_kol_id:
            logger.error("[SYNC] 创建/获取KOL失败：platform 和 platform_kol_id 是必需的。")
            return None

        try:
            existing_kol = db_session.execute(
                select(MetaKolInfo).where(
                    MetaKolInfo.platform == platform,
                    MetaKolInfo.platform_kol_id == platform_kol_id
                )
            ).scalar_one_or_none()

            now = datetime.now() # 获取当前时间用于 updated_at 和 data_last_fetched_at

            if existing_kol:
                logger.info(f"[SYNC] 找到已存在的KOL: {platform} - {platform_kol_id}，准备更新。")
                # 更新字段 (仅更新传入的字段)
                for key, value in kol_platform_data.items():
                    if hasattr(existing_kol, key) and getattr(existing_kol, key) != value:
                        setattr(existing_kol, key, value)
                        logger.debug(f"[SYNC] 更新KOL字段 {key} 为 {value}")
                existing_kol.data_last_fetched_at = now
                # existing_kol.updated_at = now # Base 模型通常会自动处理 updated_at
                kol_to_return = existing_kol
            else:
                logger.info(f"[SYNC] 未找到KOL: {platform} - {platform_kol_id}，创建新的记录。")
                # 确保所有必需的字段都存在，或提供默认值
                kol_data_for_create = {
                    "platform": platform,
                    "platform_kol_id": platform_kol_id,
                    "nickname": kol_platform_data.get("nickname"),
                    "avatar_url": kol_platform_data.get("avatar_url"),
                    "bio": kol_platform_data.get("bio"),
                    "profile_url": kol_platform_data.get("profile_url"),
                    "cover_url": kol_platform_data.get("cover_url"),
                    "gender": kol_platform_data.get("gender"),
                    "region": kol_platform_data.get("region"),
                    "city": kol_platform_data.get("city"),
                    "country": kol_platform_data.get("country"),
                    "verified": kol_platform_data.get("verified", False),
                    "verified_reason": kol_platform_data.get("verified_reason"),
                    "initial_follower_count": kol_platform_data.get("initial_follower_count", 0),
                    "initial_following_count": kol_platform_data.get("initial_following_count", 0),
                    "initial_video_count": kol_platform_data.get("initial_video_count", 0),
                    "data_last_fetched_at": now,
                    # status, memo, created_at, updated_at 会由 Base 模型或数据库默认处理
                }
                new_kol = MetaKolInfo(**kol_data_for_create)
                db_session.add(new_kol)
                kol_to_return = new_kol
            
            db_session.commit()
            if kol_to_return:
                 db_session.refresh(kol_to_return) # 确保获取到数据库生成的ID等信息
            return kol_to_return
        except sqlalchemy_exc.IntegrityError as e:
            db_session.rollback()
            logger.error(f"[SYNC] 创建/更新KOL时发生数据库完整性错误 ({platform} - {platform_kol_id}): {e}")
            return None
        except Exception as e:
            db_session.rollback()
            logger.error(f"[SYNC] 创建/更新KOL时发生未知错误 ({platform} - {platform_kol_id}): {e}", exc_info=True)
            return None

    def get_or_create_video_info_sync(self, db_session: Session, video_platform_data: Dict[str, Any], kol_id: uuid.UUID) -> Optional[MetaVideoInfo]:
        """
        [同步] 获取或创建视频元数据记录。
        如果视频已存在（基于platform和platform_video_id），则更新其信息。

        Args:
            db_session: SQLAlchemy 同步会话。
            video_platform_data: 包含视频信息的字典。至少需要 platform, platform_video_id, original_url。
            kol_id: 关联的 MetaKolInfo 的主键 (UUID)。

        Returns:
            MetaVideoInfo 对象或 None。
        """
        platform = video_platform_data.get("platform")
        platform_video_id = video_platform_data.get("platform_video_id")

        if not platform or not platform_video_id or not video_platform_data.get("original_url"):
            logger.error("[SYNC] 创建/获取视频失败：platform, platform_video_id, 和 original_url 是必需的。")
            return None
        if not kol_id:
            logger.error(f"[SYNC] 创建/获取视频失败 ({platform} - {platform_video_id}): kol_id 不能为空。")
            return None

        try:
            existing_video = db_session.execute(
                select(MetaVideoInfo).where(
                    MetaVideoInfo.platform == platform,
                    MetaVideoInfo.platform_video_id == platform_video_id
                )
            ).scalar_one_or_none()

            now = datetime.now()

            if existing_video:
                logger.info(f"[SYNC] 找到已存在的视频: {platform} - {platform_video_id}，准备更新。")
                update_dict = {k: v for k, v in video_platform_data.items() if hasattr(existing_video, k)}
                for key, value in update_dict.items():
                     if getattr(existing_video, key) != value:
                        setattr(existing_video, key, value)
                        logger.debug(f"[SYNC] 更新视频字段 {key} 为 {value}")
                existing_video.kol_id = kol_id # 确保kol_id也可能被更新
                existing_video.data_last_fetched_at = now
                video_to_return = existing_video
            else:
                logger.info(f"[SYNC] 未找到视频: {platform} - {platform_video_id}，创建新的记录。")
                video_data_for_create = {
                    "platform": platform,
                    "platform_video_id": platform_video_id,
                    "original_url": video_platform_data.get("original_url"),
                    "title": video_platform_data.get("title"),
                    "description": video_platform_data.get("description"),
                    "content_text": video_platform_data.get("content_text"),
                    "tags": video_platform_data.get("tags"),
                    "initial_play_count": video_platform_data.get("initial_play_count", 0),
                    "initial_like_count": video_platform_data.get("initial_like_count", 0),
                    "initial_comment_count": video_platform_data.get("initial_comment_count", 0),
                    "initial_share_count": video_platform_data.get("initial_share_count", 0),
                    "initial_collect_count": video_platform_data.get("initial_collect_count", 0),
                    "cover_url": video_platform_data.get("cover_url"),
                    "video_url": video_platform_data.get("video_url"),
                    "duration_seconds": video_platform_data.get("duration_seconds"),
                    "published_at": video_platform_data.get("published_at"),
                    "kol_id": kol_id,
                    "data_last_fetched_at": now,
                }
                new_video = MetaVideoInfo(**video_data_for_create)
                db_session.add(new_video)
                video_to_return = new_video
            
            db_session.commit()
            if video_to_return:
                db_session.refresh(video_to_return)
            return video_to_return
        except sqlalchemy_exc.IntegrityError as e:
            db_session.rollback()
            logger.error(f"[SYNC] 创建/更新视频时发生数据库完整性错误 ({platform} - {platform_video_id}): {e}")
            return None
        except Exception as e:
            db_session.rollback()
            logger.error(f"[SYNC] 创建/更新视频时发生未知错误 ({platform} - {platform_video_id}): {e}", exc_info=True)
            return None

    def add_daily_video_stats_sync(self, db_session: Session, video_info_id: uuid.UUID, snapshot_date: date, stats_data: Dict[str, Any]) -> Optional[StatisticsVideoDaily]:
        """
        [同步] 为指定视频添加一条新的日统计记录。
        如果当天已存在记录，则更新该记录。

        Args:
            db_session: SQLAlchemy 同步会话。
            video_info_id: MetaVideoInfo 的主键 (UUID)。
            snapshot_date: 统计快照的日期 (date 对象)。
            stats_data: 包含统计数据的字典 (play_count, like_count等)。

        Returns:
            StatisticsVideoDaily 对象或 None。
        """
        if not video_info_id or not snapshot_date or not stats_data:
            logger.error("[SYNC] 添加视频日统计失败：video_info_id, snapshot_date, 和 stats_data 不能为空。")
            return None
            
        try:
            existing_stat = db_session.execute(
                select(StatisticsVideoDaily).where(
                    StatisticsVideoDaily.video_info_id == video_info_id,
                    StatisticsVideoDaily.snapshot_date == snapshot_date
                )
            ).scalar_one_or_none()

            if existing_stat:
                logger.info(f"[SYNC] 视频日统计记录已存在 ({video_info_id} on {snapshot_date})，进行更新。")
                for key, value in stats_data.items():
                    if hasattr(existing_stat, key) and getattr(existing_stat, key) != value:
                        setattr(existing_stat, key, value)
                        logger.debug(f"[SYNC] 更新视频统计字段 {key} 为 {value}")
                # existing_stat.updated_at = datetime.now() # Base 模型会自动处理
                stat_to_return = existing_stat
            else:
                logger.info(f"[SYNC] 创建新的视频日统计记录 ({video_info_id} on {snapshot_date})。")
                daily_stat_data = {
                    "video_info_id": video_info_id,
                    "snapshot_date": snapshot_date,
                    **stats_data # 解包传入的统计数据
                }
                new_stat = StatisticsVideoDaily(**daily_stat_data)
                db_session.add(new_stat)
                stat_to_return = new_stat
            
            db_session.commit()
            if stat_to_return:
                db_session.refresh(stat_to_return)
            return stat_to_return
        except Exception as e:
            db_session.rollback()
            logger.error(f"[SYNC] 添加或更新视频日统计时发生错误 ({video_info_id} on {snapshot_date}): {e}", exc_info=True)
            return None

    def add_daily_kol_stats_sync(self, db_session: Session, kol_id: uuid.UUID, snapshot_date: date, stats_data: Dict[str, Any]) -> Optional[StatisticsKolDaily]:
        """
        [同步] 为指定KOL添加一条新的日统计记录。
        如果当天已存在记录，则更新该记录。

        Args:
            db_session: SQLAlchemy 同步会话。
            kol_id: MetaKolInfo 的主键 (UUID)。
            snapshot_date: 统计快照的日期 (date 对象)。
            stats_data: 包含KOL统计数据的字典 (follower_count, total_videos_count等)。

        Returns:
            StatisticsKolDaily 对象或 None。
        """
        if not kol_id or not snapshot_date or not stats_data:
            logger.error("[SYNC] 添加KOL日统计失败：kol_id, snapshot_date, 和 stats_data 不能为空。")
            return None

        try:
            existing_stat = db_session.execute(
                select(StatisticsKolDaily).where(
                    StatisticsKolDaily.kol_id == kol_id,
                    StatisticsKolDaily.snapshot_date == snapshot_date
                )
            ).scalar_one_or_none()

            if existing_stat:
                logger.info(f"[SYNC] KOL日统计记录已存在 ({kol_id} on {snapshot_date})，进行更新。")
                for key, value in stats_data.items():
                     if hasattr(existing_stat, key) and getattr(existing_stat, key) != value:
                        setattr(existing_stat, key, value)
                        logger.debug(f"[SYNC] 更新KOL统计字段 {key} 为 {value}")
                # existing_stat.updated_at = datetime.now()
                stat_to_return = existing_stat
            else:
                logger.info(f"[SYNC] 创建新的KOL日统计记录 ({kol_id} on {snapshot_date})。")
                daily_stat_data = {
                    "kol_id": kol_id,
                    "snapshot_date": snapshot_date,
                    **stats_data
                }
                new_stat = StatisticsKolDaily(**daily_stat_data)
                db_session.add(new_stat)
                stat_to_return = new_stat
            
            db_session.commit()
            if stat_to_return:
                db_session.refresh(stat_to_return)
            return stat_to_return
        except Exception as e:
            db_session.rollback()
            logger.error(f"[SYNC] 添加或更新KOL日统计时发生错误 ({kol_id} on {snapshot_date}): {e}", exc_info=True)
            return None

    def get_all_active_videos_sync(self, db_session: Session, page: int = 1, page_size: int = 100, platform: Optional[str] = None) -> List[MetaVideoInfo]:
        """
        [同步] 分页获取所有活跃的视频信息。

        Args:
            db_session: SQLAlchemy 同步会话。
            page: 当前页码 (从1开始)。
            page_size: 每页数量。
            platform: 可选，按平台筛选。

        Returns:
            视频信息对象列表。
        """
        offset = (page - 1) * page_size
        try:
            stmt = select(MetaVideoInfo).where(MetaVideoInfo.status == 1)
            if platform:
                stmt = stmt.where(MetaVideoInfo.platform == platform)
            
            stmt = stmt.order_by(desc(MetaVideoInfo.data_last_fetched_at), desc(MetaVideoInfo.created_at)).offset(offset).limit(page_size) #优先更新最近未更新的
            
            results = db_session.execute(stmt).scalars().all()
            logger.info(f"[SYNC] 获取到 {len(results)} 条活跃视频记录 (页码: {page}, 大小: {page_size}, 平台: {platform or '所有'})。")
            return results
        except Exception as e:
            logger.error(f"[SYNC] 分页获取活跃视频时发生错误: {e}", exc_info=True)
            return []

    def get_all_active_kols_sync(self, db_session: Session, page: int = 1, page_size: int = 100, platform: Optional[str] = None) -> List[MetaKolInfo]:
        """
        [同步] 分页获取所有活跃的KOL信息。

        Args:
            db_session: SQLAlchemy 同步会话。
            page: 当前页码 (从1开始)。
            page_size: 每页数量。
            platform: 可选，按平台筛选。

        Returns:
            KOL信息对象列表。
        """
        offset = (page - 1) * page_size
        try:
            stmt = select(MetaKolInfo).where(MetaKolInfo.status == 1)
            if platform:
                stmt = stmt.where(MetaKolInfo.platform == platform)
            
            stmt = stmt.order_by(desc(MetaKolInfo.data_last_fetched_at), desc(MetaKolInfo.created_at)).offset(offset).limit(page_size) #优先更新最近未更新的
            
            results = db_session.execute(stmt).scalars().all()
            logger.info(f"[SYNC] 获取到 {len(results)} 条活跃KOL记录 (页码: {page}, 大小: {page_size}, 平台: {platform or '所有'})。")
            return results
        except Exception as e:
            logger.error(f"[SYNC] 分页获取活跃KOL时发生错误: {e}", exc_info=True)
            return []


    def start_task_log_sync(self, db_session: Session, task_name: str, trigger_type: str = 'scheduled', items_to_process: Optional[int] = None) -> Optional[LogScheduledTaskExecution]:
        """
        [同步] 记录一个计划任务的开始。

        Args:
            db_session: SQLAlchemy 同步会话。
            task_name: 任务的名称。
            trigger_type: 任务触发类型。
            items_to_process: 预计处理的项目总数 (可选)。

        Returns:
            创建的 LogScheduledTaskExecution 对象或 None。
        """
        start_time = datetime.now()
        execution_id = uuid.uuid4() # 为本次执行生成唯一ID
        
        log_entry_data = {
            "execution_id": execution_id,
            "task_name": task_name,
            "trigger_type": trigger_type,
            "start_time": start_time,
            "status": "RUNNING", # 任务开始时状态为 RUNNING
            "items_to_process": items_to_process,
            "hostname": pf.node(), # 获取当前主机名
            "pid": os.getpid() # 获取当前进程ID
        }
        
        try:
            log_entry = LogScheduledTaskExecution(**log_entry_data)
            db_session.add(log_entry)
            db_session.commit()
            db_session.refresh(log_entry)
            logger.info(f"[TASK_LOG_SYNC] 任务 '{task_name}' (ExecID: {execution_id}) 开始执行。预计处理 {items_to_process or 'N/A'} 项。")
            return log_entry
        except Exception as e:
            db_session.rollback()
            logger.error(f"[TASK_LOG_SYNC] 记录任务 '{task_name}' 开始时失败: {e}", exc_info=True)
            return None

    def finish_task_log_sync(
        self,
        db_session: Session,
        log_entry_id: uuid.UUID, # 或者 execution_id: uuid.UUID
        status: str,
        items_succeeded: int = 0,
        items_failed: int = 0,
        items_skipped: Optional[int] = 0,
        new_items_created: Optional[int] = 0,
        items_updated: Optional[int] = 0,
        summary_details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> Optional[LogScheduledTaskExecution]:
        """
        [同步] 更新一个已开始的计划任务的结束状态和统计信息。

        Args:
            db_session: SQLAlchemy 同步会话。
            log_entry_id: 在 start_task_log_sync 中返回的记录ID (或使用 execution_id 查询)。
            status: 任务的最终状态 ('COMPLETED_SUCCESS', 'COMPLETED_PARTIAL', 'FAILED', 'CANCELLED')。
            items_succeeded: 成功处理的项目数。
            items_failed: 失败的项目数。
            items_skipped: 跳过的项目数。
            new_items_created: 新创建的项目数。
            items_updated: 更新的项目数。
            summary_details: JSONB 格式的详细摘要。
            error_message: 如果任务失败，记录错误信息。

        Returns:
            更新后的 LogScheduledTaskExecution 对象或 None。
        """
        try:
            log_entry = db_session.execute(
                select(LogScheduledTaskExecution).where(LogScheduledTaskExecution.id == log_entry_id)
                # 或者如果您更倾向于用 execution_id:
                # select(LogScheduledTaskExecution).where(LogScheduledTaskExecution.execution_id == execution_id)
            ).scalar_one_or_none()

            if not log_entry:
                logger.error(f"[TASK_LOG_SYNC] 未找到要更新的任务日志记录 (ID: {log_entry_id})。")
                return None

            log_entry.end_time = datetime.now()
            if log_entry.start_time: # 确保 start_time 存在
                 log_entry.duration_seconds = int((log_entry.end_time - log_entry.start_time).total_seconds())
            
            log_entry.status = status
            log_entry.items_succeeded = items_succeeded
            log_entry.items_failed = items_failed
            log_entry.items_skipped = items_skipped
            log_entry.new_items_created = new_items_created
            log_entry.items_updated = items_updated
            
            if summary_details:
                log_entry.summary_details = summary_details
            if error_message:
                log_entry.error_message = error_message
            
            # updated_at 会自动更新

            db_session.commit()
            db_session.refresh(log_entry)
            logger.info(f"[TASK_LOG_SYNC] 任务 '{log_entry.task_name}' (ExecID: {log_entry.execution_id}) 执行完成，状态: {status}，耗时: {log_entry.duration_seconds}s。")
            return log_entry
        except Exception as e:
            db_session.rollback()
            logger.error(f"[TASK_LOG_SYNC] 更新任务 '{getattr(log_entry, 'task_name', 'UnknownTask')}' 结束状态时失败: {e}", exc_info=True)
            return None
