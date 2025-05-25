# 在您的定时任务脚本 (例如 daily_media_updater.py)

from bot_api_v1.app.db.session import get_sync_db # 或您获取同步会话的函数
from bot_api_v1.app.services.business.media_data_service import MediaDataService # 假设 service 在这里
from bot_api_v1.app.core.logger import logger # 您的项目 logger
from datetime import date, datetime
import uuid
from bot_api_v1.app.tasks.celery_service_logic import fetch_basic_media_info # 确保导入


TASK_NAME_VIDEO_UPDATE = "daily_video_data_update"
TASK_NAME_KOL_UPDATE = "daily_kol_data_update"

def run_daily_video_update():
    media_service = MediaDataService()
    task_log_entry = None
    processed_count = 0
    succeeded_count = 0
    failed_count = 0
    new_created_count = 0
    updated_count = 0
    
    with get_sync_db() as db: 
        total_videos_to_process = media_service.get_active_videos_count_sync(db)
        task_log_entry = media_service.start_task_log_sync(
            db_session=db, 
            task_name=TASK_NAME_VIDEO_UPDATE,
            items_to_process=total_videos_to_process
        )

    if not task_log_entry:
        logger.error(f"无法为任务 {TASK_NAME_VIDEO_UPDATE} 创建开始日志，任务中止。")
        return

    current_execution_id = task_log_entry.execution_id
    logger.info(f"任务 {TASK_NAME_VIDEO_UPDATE} (ExecID: {current_execution_id}) 开始...")

    try:
        page = 1
        page_size = 100 # 您可以根据实际情况调整
        while True:
            with get_sync_db() as db: # 在循环内部为每页获取新的会话
                active_videos = media_service.get_all_active_videos_sync(db, page=page, page_size=page_size)
                if not active_videos:
                    logger.info(f"视频更新任务：没有更多活跃视频需要处理，当前页: {page}")
                    break
                
                current_page_items_count = len(active_videos)
                # processed_count += current_page_items_count # 在循环外统一更新 processed_count
                logger.info(f"视频更新任务：处理第 {page} 页，共 {current_page_items_count} 个视频...")

                for video_meta_from_db in active_videos:
                    try:
                        logger.info(f"开始处理视频: Platform={video_meta_from_db.platform}, PlatformVideoID={video_meta_from_db.platform_video_id}, DB_ID={video_meta_from_db.id}")
                        
                        # --- 调用 fetch_basic_media_info 获取最新数据 ---
                        # (这里的导入应该在文件顶部，此处仅为强调)
                        from bot_api_v1.app.tasks.celery_service_logic import fetch_basic_media_info
                        latest_data_result = fetch_basic_media_info(
                            platform=video_meta_from_db.platform,
                            url=video_meta_from_db.original_url,
                            include_comments=False,
                            user_id="system_daily_task_video", # 更具体的user_id
                            trace_id=str(current_execution_id),
                            app_id="system_tasks_app",
                            root_trace_key=str(current_execution_id)
                        )

                        if latest_data_result and latest_data_result.get("status") == "success":
                            latest_platform_data = latest_data_result.get("data")
                            if not latest_platform_data:
                                logger.warning(f"fetch_basic_media_info 未返回有效数据 for video {video_meta_from_db.platform_video_id}，跳过。")
                                failed_count += 1
                                continue

                            video_data_for_upsert = {
                                "platform": latest_platform_data.get("platform"),
                                "platform_video_id": latest_platform_data.get("video_id"),
                                "original_url": latest_platform_data.get("original_url"),
                                "title": latest_platform_data.get("title"),
                                "description": latest_platform_data.get("description"),
                                "tags": latest_platform_data.get("tags"),
                                "initial_play_count": latest_platform_data.get("statistics", {}).get("play_count"),
                                "initial_like_count": latest_platform_data.get("statistics", {}).get("like_count"),
                                "initial_comment_count": latest_platform_data.get("statistics", {}).get("comment_count"),
                                "initial_share_count": latest_platform_data.get("statistics", {}).get("share_count"),
                                "initial_collect_count": latest_platform_data.get("statistics", {}).get("collect_count"),
                                "cover_url": latest_platform_data.get("media", {}).get("cover_url"),
                                "video_url": latest_platform_data.get("media", {}).get("video_url"),
                                "duration_seconds": latest_platform_data.get("media", {}).get("duration"),
                                "published_at": datetime.fromisoformat(latest_platform_data["publish_time"].replace("Z", "+00:00")) if latest_platform_data.get("publish_time") else None,
                            }
                            
                            kol_info_from_video = latest_platform_data.get("author")
                            kol_obj = None
                            if kol_info_from_video and kol_info_from_video.get("id"):
                                kol_platform_data_for_upsert = {
                                    "platform": latest_platform_data.get("platform"), # KOL平台应与视频平台一致
                                    "platform_kol_id": kol_info_from_video.get("id"),
                                    "nickname": kol_info_from_video.get("nickname"),
                                    "avatar_url": kol_info_from_video.get("avatar"),
                                    "profile_url": kol_info_from_video.get("profile_url"), 
                                }
                                kol_obj = media_service.get_or_create_kol_info_sync(db, kol_platform_data_for_upsert)

                            if not kol_obj:
                                logger.error(f"无法获取或创建视频 {video_meta_from_db.platform_video_id} 的作者信息。当前作者信息: {kol_info_from_video}")
                                failed_count +=1
                                continue
                            
                            updated_video_obj = media_service.get_or_create_video_info_sync(
                                db, 
                                video_data_for_upsert, 
                                kol_obj.id 
                            )

                            if not updated_video_obj:
                                logger.error(f"更新/创建视频元数据失败: {video_meta_from_db.platform_video_id}")
                                failed_count += 1
                                continue
                            
                            # 判断是新增还是更新
                            is_newly_created = updated_video_obj.created_at > video_meta_from_db.created_at
                            was_updated = not is_newly_created and updated_video_obj.updated_at > video_meta_from_db.updated_at
                            
                            if is_newly_created:
                                new_created_count +=1
                            elif was_updated: # 只有在不是新创建且确实更新了的情况下才算更新
                                updated_count +=1
                            
                            stats_for_daily_log = {
                                "play_count": latest_platform_data.get("statistics", {}).get("play_count", 0),
                                "like_count": latest_platform_data.get("statistics", {}).get("like_count", 0),
                                "comment_count": latest_platform_data.get("statistics", {}).get("comment_count", 0),
                                "share_count": latest_platform_data.get("statistics", {}).get("share_count", 0),
                                "collect_count": latest_platform_data.get("statistics", {}).get("collect_count", 0),
                            }
                            media_service.add_daily_video_stats_sync(db, updated_video_obj.id, date.today(), stats_for_daily_log)
                            succeeded_count += 1
                        else:
                            logger.warning(f"调用 fetch_basic_media_info 获取视频 {video_meta_from_db.platform_video_id} 最新数据失败: {latest_data_result.get('error')}")
                            failed_count += 1
                            continue
                    except Exception as item_error:
                        failed_count += 1
                        logger.error(f"处理视频 {getattr(video_meta_from_db, 'platform_video_id', 'UNKNOWN_ID')} 失败: {item_error}", exc_info=True)
                
                processed_count += current_page_items_count # 更新已扫描的总数
                page += 1
                if page > 5000: 
                    logger.warning(f"视频更新任务：已达到最大处理页数 {page-1}，任务提前结束。")
                    break
        
        final_status = 'COMPLETED_PARTIAL' if failed_count > 0 else 'COMPLETED_SUCCESS'
        with get_sync_db() as db:
            media_service.finish_task_log_sync(
                db_session=db,
                log_entry_id=task_log_entry.id,
                status=final_status,
                items_succeeded=succeeded_count,
                items_failed=failed_count,
                new_items_created=new_created_count,
                items_updated=updated_count,
                # items_to_process 应该在任务开始时已经估算并记录，这里可以记录实际扫描的总数
                summary_details={"total_pages_processed": page -1, "total_items_scanned_from_db": processed_count}
            )
    except Exception as task_general_error:
        logger.error(f"任务 {TASK_NAME_VIDEO_UPDATE} (ExecID: {current_execution_id}) 整体执行失败: {task_general_error}", exc_info=True)
        if task_log_entry:
            with get_sync_db() as db:
                items_to_process_val = task_log_entry.items_to_process if task_log_entry.items_to_process is not None else processed_count
                remaining_failed = items_to_process_val - succeeded_count - failed_count
                total_failed = failed_count + max(0, remaining_failed)
                media_service.finish_task_log_sync(
                    db_session=db,
                    log_entry_id=task_log_entry.id,
                    status='FAILED',
                    items_succeeded=succeeded_count,
                    items_failed=total_failed,
                    new_items_created=new_created_count,
                    items_updated=updated_count,
                    error_message=f"任务执行期间发生严重错误: {str(task_general_error)}"
                )

# --- 新增：每日KOL数据更新任务 ---
def run_daily_kol_update():
    media_service = MediaDataService()
    task_log_entry = None
    processed_count = 0
    succeeded_count = 0
    failed_count = 0
    new_created_count = 0
    updated_count = 0

    # 1. 任务开始时记录
    with get_sync_db() as db:
        total_kols_to_process = media_service.get_active_kols_count_sync(db) # 获取活跃KOL总数
        task_log_entry = media_service.start_task_log_sync(
            db_session=db,
            task_name=TASK_NAME_KOL_UPDATE,
            items_to_process=total_kols_to_process
        )

    if not task_log_entry:
        logger.error(f"无法为任务 {TASK_NAME_KOL_UPDATE} 创建开始日志，任务中止。")
        return

    current_execution_id = task_log_entry.execution_id
    logger.info(f"任务 {TASK_NAME_KOL_UPDATE} (ExecID: {current_execution_id}) 开始...")

    try:
        page = 1
        page_size = 100  # 您可以根据实际情况调整
        while True:
            with get_sync_db() as db: # 在循环内部为每页获取新的会话
                active_kols = media_service.get_all_active_kols_sync(db, page=page, page_size=page_size)
                if not active_kols:
                    logger.info(f"KOL更新任务：没有更多活跃KOL需要处理，当前页: {page}")
                    break
                
                current_page_items_count = len(active_kols)
                logger.info(f"KOL更新任务：处理第 {page} 页，共 {current_page_items_count} 个KOL...")

                for kol_meta_from_db in active_kols:
                    try:
                        logger.info(f"开始处理KOL: Platform={kol_meta_from_db.platform}, PlatformKolID={kol_meta_from_db.platform_kol_id}, DB_ID={kol_meta_from_db.id}")

                        # 1. 调用 MediaDataService 的 get_full_kol_info_sync 获取最新的、完整的KOL主页信息
                        #    这个方法内部会负责从源平台抓取数据并更新/创建 MetaKolInfo 记录
                        #    它需要 db_session, platform, platform_kol_id, 和可选的 kol_profile_url
                        latest_kol_obj_from_platform = media_service.get_full_kol_info_sync(
                            db_session=db, # 传递当前会话
                            platform=kol_meta_from_db.platform,
                            platform_kol_id=kol_meta_from_db.platform_kol_id,
                            kol_profile_url=kol_meta_from_db.profile_url # 如果有存储，可以传递
                        )

                        if not latest_kol_obj_from_platform:
                            logger.warning(f"未能从源平台获取或更新KOL {kol_meta_from_db.platform_kol_id} 的最新数据，跳过统计。")
                            failed_count += 1
                            continue
                        
                        # 判断是新增还是更新 (latest_kol_obj_from_platform 是 get_or_create_kol_info_sync 返回的DB对象)
                        is_newly_created = latest_kol_obj_from_platform.created_at > kol_meta_from_db.created_at
                        was_updated = not is_newly_created and latest_kol_obj_from_platform.updated_at > kol_meta_from_db.updated_at

                        if is_newly_created:
                            new_created_count += 1
                        elif was_updated:
                            updated_count += 1
                        
                        # 2. 准备用于 StatisticsKolDaily 的数据
                        #    这些数据应该从 latest_kol_obj_from_platform (即最新的KOL元数据) 中提取
                        #    例如，如果 get_full_kol_info_sync 更新了 initial_follower_count 等字段为最新值
                        stats_for_daily_kol_log = {
                            "follower_count": latest_kol_obj_from_platform.initial_follower_count or 0,
                            "following_count": latest_kol_obj_from_platform.initial_following_count or 0,
                            "total_videos_count": latest_kol_obj_from_platform.initial_video_count or 0,
                            # 以下字段需要您的平台抓取服务能提供，如果不能，则默认为0或从其他地方计算
                            "total_likes_received_on_videos": latest_kol_obj_from_platform.total_likes_received_on_videos or 0, # 假设模型有此字段
                            "total_comments_received_on_videos": latest_kol_obj_from_platform.total_comments_received_on_videos or 0,
                            "total_shares_on_videos": latest_kol_obj_from_platform.total_shares_on_videos or 0,
                            "total_collections_on_videos": latest_kol_obj_from_platform.total_collections_on_videos or 0,
                            "total_plays_on_videos": latest_kol_obj_from_platform.total_plays_on_videos or 0,
                        }
                        
                        media_service.add_daily_kol_stats_sync(db, latest_kol_obj_from_platform.id, date.today(), stats_for_daily_kol_log)
                        
                        succeeded_count += 1
                        logger.info(f"KOL {kol_meta_from_db.platform_kol_id} 数据更新成功。")

                    except Exception as item_error:
                        failed_count += 1
                        logger.error(f"处理KOL {getattr(kol_meta_from_db, 'platform_kol_id', 'UNKNOWN_ID')} 失败: {item_error}", exc_info=True)
                
                processed_count += current_page_items_count # 更新已扫描的总数
                page += 1
                if page > 2000: # 假设最多处理 2000 * 100 = 20万条记录
                    logger.warning(f"KOL更新任务：已达到最大处理页数 {page-1}，任务提前结束。")
                    break

        final_status = 'COMPLETED_PARTIAL' if failed_count > 0 else 'COMPLETED_SUCCESS'
        with get_sync_db() as db:
            media_service.finish_task_log_sync(
                db_session=db,
                log_entry_id=task_log_entry.id,
                status=final_status,
                items_succeeded=succeeded_count,
                items_failed=failed_count,
                new_items_created=new_created_count,
                items_updated=updated_count,
                summary_details={"total_pages_processed": page - 1, "total_items_scanned_from_db": processed_count}
            )

    except Exception as task_general_error:
        logger.error(f"任务 {TASK_NAME_KOL_UPDATE} (ExecID: {current_execution_id}) 整体执行失败: {task_general_error}", exc_info=True)
        if task_log_entry:
            with get_sync_db() as db:
                items_to_process_val = task_log_entry.items_to_process if task_log_entry.items_to_process is not None else processed_count
                remaining_failed = items_to_process_val - succeeded_count - failed_count
                total_failed = failed_count + max(0, remaining_failed)
                media_service.finish_task_log_sync(
                    db_session=db,
                    log_entry_id=task_log_entry.id,
                    status='FAILED',
                    items_succeeded=succeeded_count,
                    items_failed=total_failed,
                    new_items_created=new_created_count,
                    items_updated=updated_count,
                    error_message=f"任务执行期间发生严重错误: {str(task_general_error)}"
                )