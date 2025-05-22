from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger
from openai import OpenAI
import time

import json
import asyncio # 用于异步sleep
from typing import List, Dict, Any
from openai import AsyncOpenAI # <--- 注意：为了异步操作，这里应该用 AsyncOpenAI
from bot_api_v1.app.core.cache import async_cache_result


class OpenRouterService:
    def __init__(self):
        self.api_key = settings.OPEN_ROUTER_API_KEY_QW
        self.model = settings.OPEN_ROUTER_API_MODEL_QW
        self.base_url = settings.OPEN_ROUTER_API_URL

        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        self.async_client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
    
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


    @async_cache_result(expire_seconds=600, prefix="open-router")
    async def get_keywords_for_wordcloud(
        self,
        note_list: List[Dict[str, Any]],
        task_id: str,
        log_extra: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        从笔记列表中提取标题，发送给AI获取用于词云的关键词及其频率。
        """
        logger.info(f"[{task_id}] 开始为词云提取关键词。", extra=log_extra)

        if not isinstance(note_list, list): # 基础校验
            logger.error(f"[{task_id}] note_list 不是一个列表。", extra=log_extra)
            return {"success": False, "error": "note_list参数必须是列表", "keywords": []}
        if not all(isinstance(note, dict) for note in note_list):
            logger.error(f"[{task_id}] note_list 包含非字典元素。", extra=log_extra)
            return {"success": False, "error": "note_list中的元素必须是字典", "keywords": []}

        titles = []
        for note in note_list:
            # 根据你之前 note_list 的示例，标题在 'display_title'
            title = note.get("display_title")
            if title and isinstance(title, str) and title.strip():
                titles.append(title.strip())

        if not titles:
            logger.warning(f"[{task_id}] note_list 中没有可供提取的标题。", extra=log_extra)
            return {"success": True, "message": "笔记列表中没有可供提取的标题", "keywords": []}

        # 将所有标题合并为一个文本块，用换行符分隔
        concatenated_titles = "\n".join(titles)
        
        # 考虑对标题总长度进行限制，避免Prompt过长超出模型限制
        # 这个最大长度需要根据你使用的模型token限制来调整
        max_prompt_char_length = 3800 # 示例字符数限制
        if len(concatenated_titles) > max_prompt_char_length:
            logger.warning(f"[{task_id}] 连接后的标题长度 ({len(concatenated_titles)}) 超出限制 ({max_prompt_char_length})，将被截断。", extra=log_extra)
            concatenated_titles = concatenated_titles[:max_prompt_char_length]

        # 为AI设计的Prompt，要求它返回JSON格式的关键词和频率
        wordcloud_prompt = f"""你是一位专业的文本分析师和数据洞察专家。请仔细阅读并分析以下中文内容（这是一份笔记标题列表）：
---
{concatenated_titles}
---
你的任务是：
1. 提取出其中最核心、最能代表内容主题的关键词或短语。
2. 评估每个关键词/短语的相对重要性或出现频率，并给出一个数值（整数）。
3. 以JSON列表的格式返回结果，列表中每个对象应包含 "text" (关键词/短语字符串) 和 "value" (重要性/频率数值) 两个字段。

请确保返回的是一个结构良好、可以直接被程序解析的JSON数组。不要在JSON内容之外添加任何解释性文字、代码块标记（如```json）或注释。

例如，如果标题内容多样，你可能返回：
[
  {{"text": "懒人食谱", "value": 28}},
  {{"text": "空气炸锅", "value": 22}},
  {{"text": "葱油拌面", "value": 19}},
  {{"text": "美食教程", "value": 15}}
]
"""
        keywords_list = []
        retry_count = 3
        last_exception_str = "未知错误"

        for attempt in range(retry_count):
            try:
                logger.info(f"[{task_id}] 尝试第 {attempt + 1} 次从AI获取词云关键词。", extra=log_extra)
                
                # 使用异步客户端调用
                completion = await self.async_client.chat.completions.create(
                    extra_headers={
                        "HTTP-Referer": "xiaoshanqing",
                        "X-Title": "xiao",
                    },
                    model=self.model, # 可以为关键词提取指定不同模型
                    messages=[
                        {"role": "user", "content": wordcloud_prompt}
                    ],
                    temperature=0.2, # 较低的温度有助于生成更稳定、一致的关键词
                    # response_format={ "type": "json_object" }, # 如果模型和客户端支持，可以尝试此参数强制JSON输出
                )

                content_str = completion.choices[0].message.content if completion and completion.choices else ""
                
                if content_str:
                    logger.info(f"[{task_id}] AI为关键词提取返回的原始文本: {content_str[:500]}...", extra=log_extra) # 日志中只记录部分，避免过长
                    
                    # 尝试清理AI返回内容中可能包含的Markdown代码块标记
                    cleaned_content_str = content_str.strip()
                    if cleaned_content_str.startswith("```json"):
                        cleaned_content_str = cleaned_content_str[7:]
                        if cleaned_content_str.endswith("```"):
                            cleaned_content_str = cleaned_content_str[:-3]
                    elif cleaned_content_str.startswith("```"): # 有些模型可能只用 ```
                        cleaned_content_str = cleaned_content_str[3:]
                        if cleaned_content_str.endswith("```"):
                            cleaned_content_str = cleaned_content_str[:-3]
                    
                    cleaned_content_str = cleaned_content_str.strip()

                    try:
                        keywords_list = json.loads(cleaned_content_str)
                        # 验证返回的是否是期望的格式：一个包含字典的列表，且字典包含'text'和'value'
                        if isinstance(keywords_list, list) and \
                           all(isinstance(kw, dict) and "text" in kw and "value" in kw for kw in keywords_list):
                            logger.info(f"[{task_id}] 成功解析AI返回的关键词数据。", extra=log_extra)
                            return {"success": True, "keywords": keywords_list}
                        else:
                            logger.error(f"[{task_id}] AI返回的关键词数据格式不正确 (非对象列表或缺少键)。解析后数据: {keywords_list}", extra=log_extra)
                            last_exception_str = "AI返回的关键词数据格式不正确"
                    except json.JSONDecodeError as json_e:
                        logger.error(f"[{task_id}] 解析AI返回的关键词JSON时失败 (尝试 {attempt + 1}): {json_e}. AI原始返回(清理后): {cleaned_content_str}", extra=log_extra)
                        last_exception_str = f"JSON解析失败: {json_e}"
                else:
                    logger.warning(f"[{task_id}] AI为关键词提取返回空内容 (尝试 {attempt + 1})。", extra=log_extra)
                    last_exception_str = "AI返回空内容"

            except Exception as e:
                logger.error(f"[{task_id}] 调用AI获取关键词时发生异常 (尝试 {attempt + 1}): {type(e).__name__} - {str(e)}", exc_info=True, extra=log_extra)
                last_exception_str = f"{type(e).__name__}: {str(e)}"
            
            if attempt < retry_count - 1:
                await asyncio.sleep(2) # 异步等待
            else: # 所有重试均失败
                logger.error(f"[{task_id}] 尝试 {retry_count} 次后，仍未能从AI获取有效的关键词数据。最后错误: {last_exception_str}", extra=log_extra)
                return {"success": False, "error": f"AI关键词提取失败: {last_exception_str}", "keywords": []}
        
        # 理论上不应执行到这里，但作为保险
        return {"success": False, "error": "提取关键词时发生未知错误。", "keywords": []}
