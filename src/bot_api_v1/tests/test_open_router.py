from openai import OpenAI
from bot_api_v1.app.core.config import settings

client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=settings.OPEN_ROUTER_API_KEY_QW,
)

completion = client.chat.completions.create(
  extra_headers={
    "HTTP-Referer": "www.xiaoshanqing.tech", # Optional. Site URL for rankings on openrouter.ai.
    "X-Title": "xiao", # Optional. Site title for rankings on openrouter.ai.
  },
  extra_body={},
  model="qwen/qwen3-30b-a3b:free",
#   model="google/gemini-2.5-pro-exp-03-25",
  messages=[
    {
      "role": "user",
      "content": "你好，协助做一些数学题"
    }
  ]
)
print(completion.choices[0].message.content)