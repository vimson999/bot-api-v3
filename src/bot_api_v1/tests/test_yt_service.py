from bot_api_v1.app.services.business.yt_dlp_service import YtDLP_Service_Sync
import json
import requests 
from requests.exceptions import RequestException # 导入 requests 的异常类

# # --- 示例用法 ---
if __name__ == "__main__":
    # 定义测试用例字典，key为平台名，value为测试链接
    test_urls = {
        "douyin": "https://www.douyin.com/video/7475254041207950642",
        # "tiktok": "https://www.tiktok.com/t/ZP8jq1GVP/",
        # "kuaishou": "https://www.kuaishou.com/f/X-MGnYq0BTJfH0y",
        # "kuaishou": "https://www.kuaishou.com/f/X34s4ikwqfv7vZN",

        # "bilibili": "https://www.bilibili.com/video/BV1EV5iznEQZ?spm_id_from=333.1007.tianma.3-2-6.click",
        # "instagram": "https://www.instagram.com/p/DIrTqrbvVHS/?igsh=MTdmeTBrZnVkODkycQ==",
        # "youtube": "https://www.youtube.com/watch?v=c7IVaQi643g"
    }
    get_content = True
    # get_content = False

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
                PROMPTS = {
                    "core": "请你化身**顶尖爆款视频策划人**，以制造刷屏级内容的敏锐嗅觉，审视并提炼出我给你文字中最具冲击力、最能引发用户共鸣和传播的核心观点/价值点。请用简洁精炼的语言，分点列出，并简要阐述每个观点**为何具备成为爆款的潜质**（例如：情感触发点、争议性、实用价值、新奇度、反差感等）。给你的文字是：",
                    "formula": "请你扮演一位**深谙传播之道的爆款视频操盘手**，对我给你的文字进行深度解剖，提炼总结出其中可被复用、可迁移的**“爆款密码”或“增长范式”**。请清晰阐述这个“范式”的关键组成部分（如：钩子设计、情绪曲线、价值点呈现节奏、互动引导策略、记忆点打造技巧等），并说明**如何将其巧妙应用于其他内容的创作中**，以显著提升引爆流行、实现增长的可能性。给你的文字是：",
                    "copywriting": """请你以**深谙小红书平台特性与用户心理的资深内容运营专家**身份，围绕我给你的文字，创作一篇**至少100字**、**极具“网感”和“种草力”**的小红书爆款笔记文案。要求：
    1.  **开头3秒吸睛**，瞬间抓住用户注意力。
    2.  **语言生动、场景化**，多使用**emoji**表情符号，营造沉浸式体验。
    3.  **价值点清晰、痛点共鸣**，巧妙植入核心信息。
    4.  **包含3-5个相关热门#话题标签#**，提升曝光潜力。
    5.  **结尾设置巧妙的互动引导**（如提问、投票、求助、号召行动等）。
    请产出**2-3个不同风格或侧重点的文案版本**，供我挑选优化。,给你的文字是：""",
                    "golden3s": """请你作为**精通“黄金三秒”法则、能瞬间点燃用户好奇心的爆款视频大师**，针对我给你的文字，构思**3-5个**能够在**视频开篇3秒内**就**牢牢锁住观众眼球、激发强烈观看欲望**的**创意开场方案**。请具体描述每个方案的：
    * **核心悬念/钩子**
    并简要阐述每个方案**为何能有效抓住注意力并驱动用户继续观看**。我给你的文字是：
                    """
                }

                content_text = '这款声音课能工具太离谱了做着体现声明不允许用这个模型感违法的事儿我们看一下这课能声音到底有多像听下马云的我们每个人都在追求不同的目标很多人认为还有特朗普的但AI是动作的这个模型的优点是不需要给到声音做额外的训练连呼吸节奏都能控制您合成技术其实早已经悄悄走进了我们的生活这边还有安装收明Windows可以在这里直接下来学用我这边已经安装好了上面是我上南小阳歌的生意其实我很多事我已经做不了了所以我有一段时间我非常焦虑我压力非常大目标文文你也写上我们随意要课轮的话点击试能移民就可以了天天效果兄弟们我马上要回来了你们还支持我吗你们觉得这个效果怎么样'
                print(f'content_text is {content_text}')

                from openai import OpenAI
                from bot_api_v1.app.services.business.open_router_service import OpenRouterService
                openai_service = OpenRouterService()
                for key in ["core", "formula", "copywriting", "golden3s"]:
                    try:
                        role = PROMPTS[key]
                        ai_result = openai_service.get_ai_assistant_text(role, trace_id, content_text, {})
                        # 可根据 key 分类处理 ai_result

                        print(f'ai_assitent is {ai_result}')
                    except Exception as e:
                        print(f"调用 OpenAI API 时发生异常: {e}")
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