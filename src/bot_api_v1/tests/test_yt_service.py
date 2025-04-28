from bot_api_v1.app.services.business.yt_dlp_service import YtDLP_Service_Sync
import json

# # --- 示例用法 ---
if __name__ == "__main__":
    # 定义测试用例字典，key为平台名，value为测试链接
    test_urls = {
        "douyin": "https://www.douyin.com/video/7475254041207950642",
        "tiktok": "https://www.tiktok.com/t/ZP8jq1GVP/",
        # "kuaishou": "https://www.kuaishou.com/f/X-MGnYq0BTJfH0y",

        # "bilibili": "https://www.bilibili.com/video/BV1EV5iznEQZ?spm_id_from=333.1007.tianma.3-2-6.click",
        # "instagram": "https://www.instagram.com/p/DIrTqrbvVHS/?igsh=MTdmeTBrZnVkODkycQ==",
        # "youtube": "https://www.youtube.com/watch?v=c7IVaQi643g"
    }
    # get_content = True
    get_content = False

    yt_sync_service = YtDLP_Service_Sync()

    for platform, test_url in test_urls.items():
        print(f"\n=================================== 测试平台: {platform} ===================================\n")
        try:
            if platform == "douyin":
                from bot_api_v1.app.tasks.celery_tiktok_service import CeleryTikTokService
                tiktok_service = CeleryTikTokService()      

                user_id = ''
                trace_id = "test_trace_id"

                media_data = tiktok_service.get_basic_video_info_sync_internal(
                    url=test_url,
                    extract_text=get_content,
                    user_id_for_points=user_id,
                    trace_id=trace_id
                )    
            else:
                video_info = yt_sync_service.test_full(test_url,get_content)
                if video_info:
                    print("\n--- 视频基础信息 ---")
                    print(json.dumps(video_info, indent=4, ensure_ascii=False))
                else:
                    print(f"\n无法获取视频信息: {test_url}")
        except Exception as e:
            print(f"测试 {platform} 时发生异常: {e}")