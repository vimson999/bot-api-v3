from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger
from openai import OpenAI
import time

class OpenRouterService:
    def __init__(self):
        self.api_key = settings.OPEN_ROUTER_API_KEY_QW
        self.model = settings.OPEN_ROUTER_API_MODEL_QW
        self.base_url = settings.OPEN_ROUTER_API_URL
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    
    def get_ai_assistant_text(
        self,
        # role: str,
        task_id: str,
        origin_content: str,
        log_extra: dict
    ):
        """
        调用大模型生成AI助理文本，支持自定义模型、API Key和Base URL。
        """
        # if not role or not isinstance(role, str):
        #     logger.error(f"[{task_id}] get_ai_assistant_text: role参数无效", extra=log_extra)
        #     return {"success": False, "error": "role参数无效"}
        if not origin_content or not isinstance(origin_content, str):
            logger.error(f"[{task_id}] get_ai_assistant_text: origin_content参数无效", extra=log_extra)
            return {"success": False, "error": "origin_content参数无效"}
            
        try:
            _model = self.model
            _api_key = self.api_key 
            _base_url = self.base_url

            # logger.info(f"ai content is {role}")
            PROMPTS = {
                    "core": f"请你化身**顶尖爆款视频策划人**，以制造刷屏级内容的敏锐嗅觉，审视并提炼出**[{origin_content}]**中最具冲击力、最能引发用户共鸣和传播的核心观点/价值点。请用简洁精炼的语言，分点列出，并简要阐述每个观点**为何具备成为爆款的潜质**（例如：情感触发点、争议性、实用价值、新奇度、反差感等）。",
                    "formula": f"请你扮演一位**深谙传播之道的爆款视频操盘手**，对**[{origin_content}]**进行深度解剖，提炼总结出其中可被复用、可迁移的**“爆款密码”或“增长范式”**。请清晰阐述这个“范式”的关键组成部分（如：钩子设计、情绪曲线、价值点呈现节奏、互动引导策略、记忆点打造技巧等），并说明**如何将其巧妙应用于其他内容的创作中**，以显著提升引爆流行、实现增长的可能性。",
                    "copywriting": f"""请你以**深谙小红书平台特性与用户心理的资深内容运营专家**身份，围绕这段文字**[{origin_content}]**，创作一篇**至少100字**、**极具“网感”和“种草力”**的小红书爆款笔记文案。要求：
    1.  **开头3秒吸睛**，瞬间抓住用户注意力。
    2.  **语言生动、场景化**，多使用**emoji**表情符号，营造沉浸式体验。
    3.  **价值点清晰、痛点共鸣**，巧妙植入核心信息。
    4.  **包含3-5个相关热门#话题标签#**，提升曝光潜力。
    5.  **结尾设置巧妙的互动引导**（如提问、投票、求助、号召行动等）。
    请产出**2-3个不同风格或侧重点的文案版本**，供我挑选优化。""",
                    "golden3s": f"""⏱️ **黄金3秒 · 夺目开局策划** ⏱️
请你作为**精通“黄金三秒”法则、能瞬间点燃用户好奇心的爆款视频大师**，针对这段文字**[{origin_content}]**，构思**3-5个**能够在**视频开篇3秒内**就**牢牢锁住观众眼球、激发强烈观看欲望**的**创意开场方案**。请具体描述每个方案的：
    * **核心悬念/钩子**
    并简要阐述每个方案**为何能有效抓住注意力并驱动用户继续观看**
                    """
                }

            ai_dict = {}
            for key in ["core", "formula", "copywriting", "golden3s"]:
                retry_count = 3
                for attempt in range(retry_count):
                    try:
                        play = PROMPTS[key]
                        completion = self.client.chat.completions.create(
                            extra_headers={
                                "HTTP-Referer": "xiaoshanqing",
                                "X-Title": "xiao",
                            },
                            extra_body={},
                            model=self.model,
                            messages=[
                                {
                                    "role": "user",
                                    "content": f"{play}"
                                }
                            ]
                        )

                        content = completion.choices[0].message.content if completion and completion.choices else ""
                        if content:
                            logger.info(f'ai_assitent role {key} result {content}')
                            ai_dict[key] = content
                            break  # 成功则跳出重试循环
                        else:
                            logger.warning(f"第{attempt+1}次请求OpenAI API返回空内容，role={key}", extra=log_extra)
                    except Exception as e:
                        logger.info(f"第{attempt+1}次调用 OpenAI API 时发生异常: {e}")
                    
                    if attempt < retry_count - 1:
                        time.sleep(2)  # 等待2秒后重试
                else:
                    ai_dict[key] = ""
            
            logger.info(f"[{task_id}] get_ai_assistant_text: AI返回内容={ai_dict}", extra=log_extra)
            return {"status": "success", "content": ai_dict}
        except Exception as e:
            logger.error(f"[{task_id}] get_ai_assistant_text异常: {type(e).__name__} - {str(e)}", exc_info=True, extra=log_extra)
            return {"success": False, "error": str(e)}


