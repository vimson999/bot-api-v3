from bot_api_v1.app.services.business.yt_dlp_service import YtDLP_Service_Sync
import json
import requests 
from requests.exceptions import RequestException # 导入 requests 的异常类

# # --- 示例用法 ---
if __name__ == "__main__":
    # 定义测试用例字典，key为平台名，value为测试链接
    test_urls = {
        # "douyin": "https://www.douyin.com/video/7475254041207950642",
        "tiktok": "https://www.tiktok.com/t/ZP8jq1GVP/",
        # "kuaishou": "https://www.kuaishou.com/f/X-MGnYq0BTJfH0y",
        # "kuaishou": "https://www.kuaishou.com/f/X34s4ikwqfv7vZN",

        # "bilibili": "https://www.bilibili.com/video/BV1EV5iznEQZ?spm_id_from=333.1007.tianma.3-2-6.click",
        "instagram": "https://www.instagram.com/p/DIrTqrbvVHS/?igsh=MTdmeTBrZnVkODkycQ==",
        "youtube": "https://www.youtube.com/watch?v=c7IVaQi643g"
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

                video_info = media_data # 你可能需要调整这里的数据结构
            elif platform == "kuaishou":
                kuaishou_api_endpoint = "http://127.0.0.1:9000/info" # API 服务地址
                payload = {"url": test_url} # 请求体
                headers = {"Content-Type": "application/json"}
                print(f"调用 Kuaishou API: {kuaishou_api_endpoint} for URL: {test_url}")

                try:
                    # 发送 POST 请求到 API
                    response = requests.post(kuaishou_api_endpoint, headers=headers, json=payload, timeout=30) # 设置超时
                    response.raise_for_status() # 如果状态码不是 2xx，则抛出异常

                    # 解析 JSON 响应
                    api_response = response.json()
                    if api_response.get("status") == "success" and api_response.get("data"):
                        video_info = api_response["data"] # 提取 video_info 部分
                        print("Kuaishou API 调用成功，获取到信息。")
                    else:
                        # API 返回成功但没有 video_info 或 status 不是 success
                        print(f"Kuaishou API 调用完成，但未能获取有效视频信息: {api_response.get('message')}")

                except RequestException as e:
                    # 处理网络请求错误 (连接错误、超时等)
                    print(f"调用 Kuaishou API 时发生网络错误: {e}")
                except json.JSONDecodeError:
                    # 处理 API 返回非 JSON 格式的情况
                    print(f"Kuaishou API 返回了无效的 JSON 响应: {response.text}")
                except Exception as api_err:
                    # 处理其他可能的错误
                    print(f"调用 Kuaishou API 时发生未知错误: {api_err}")

            # ========================================     
            else:
                video_info = yt_sync_service.test_full(test_url,get_content)

            if video_info:
                print("\n--- 视频基础信息 ---")
                print(json.dumps(video_info, indent=4, ensure_ascii=False))
            else:
                print(f"\n无法获取视频信息: {test_url}")
        except Exception as e:
            print(f"测试 {platform} 时发生异常: {e}")