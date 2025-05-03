from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger
from openai import OpenAI


class OpenRouterService:
    def __init__(self):
        self.api_key = settings.OPEN_ROUTER_API_KEY_QW
        self.model = settings.OPEN_ROUTER_API_MODEL_QW
        self.base_url = settings.OPEN_ROUTER_API_URL
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    
    def get_ai_assistant_text(
        self,
        role: str,
        task_id: str,
        origin_content: str,
        log_extra: dict
    ):
        """
        调用大模型生成AI助理文本，支持自定义模型、API Key和Base URL。
        """
        if not role or not isinstance(role, str):
            logger.error(f"[{task_id}] get_ai_assistant_text: role参数无效", extra=log_extra)
            return {"success": False, "error": "role参数无效"}
        if not origin_content or not isinstance(origin_content, str):
            logger.error(f"[{task_id}] get_ai_assistant_text: origin_content参数无效", extra=log_extra)
            return {"success": False, "error": "origin_content参数无效"}
            
        try:
            _model = self.model
            _api_key = self.api_key 
            _base_url = self.base_url
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
                        "content": f"{role}，{origin_content}"
                    }
                ]
            )

            content = completion.choices[0].message.content if completion and completion.choices else ""
            logger.info(f"[{task_id}] get_ai_assistant_text: AI返回内容长度={len(content)}", extra=log_extra)
            return {"success": True, "content": content}
        except Exception as e:
            logger.error(f"[{task_id}] get_ai_assistant_text异常: {type(e).__name__} - {str(e)}", exc_info=True, extra=log_extra)
            return {"success": False, "error": str(e)}


