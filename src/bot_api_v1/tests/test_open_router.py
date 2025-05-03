from openai import OpenAI
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.services.business import yt_dlp_service
from bot_api_v1.app.services.business.yt_dlp_service import YtDLP_Service_Sync


def test_open_router(origin_content : str = "你好"):    
  client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.OPEN_ROUTER_API_KEY_QW,
  )

  completion = client.chat.completions.create(
    extra_headers={
      "HTTP-Referer": "xiaoshanqing", # Optional. Site URL for rankings on openrouter.ai.
      "X-Title": "xiao", # Optional. Site title for rankings on openrouter.ai.
    },
    extra_body={},
    model=settings.OPEN_ROUTER_API_MODEL_QW,
  #   model="google/gemini-2.5-pro-exp-03-25",
    messages=[
      {
        "role": "user",
        "content": f"你好，作为一个资深媒体运营专家，擅长制造爆款视频，请你帮我提炼这段文字的核心观点，{origin_content}"
      }
    ]
  )

  content = completion.choices[0].message.content
  print( f'content is {content}')

  return content


def test_get_transcribed_text(origin_content : str = "你好"):
    yt_dlp_service = YtDLP_Service_Sync()

    task_id = '1'
    log_extra = {
      
    }
    role = '你好，作为一个资深媒体运营专家，擅长制造爆款视频，请你帮我提炼这段文字的核心观点'
    an = yt_dlp_service.get_ai_assistant_text(role,task_id,origin_content,log_extra)
    print(f'an is {an}')

if __name__ == "__main__":
  content = '这款声音课能工具太离谱了做着体现声明不允许用这个模型感违法的事儿我们看一下这课能声音到底有多像听下马云的我们每个人都在追求不同的目标很多人认为还有特朗普的但AI是动作的这个模型的优点是不需要给到声音做额外的训练连呼吸节奏都能控制您合成技术其实早已经悄悄走进了我们的生活这边还有安装收明Windows可以在这里直接下来学用我这边已经安装好了上面是我上南小阳歌的生意其实我很多事我已经做不了了所以我有一段时间我非常焦虑我压力非常大目标文文你也写上我们随意要课轮的话点击试能移民就可以了天天效果兄弟们我马上要回来了你们还支持我吗你们觉得这个效果怎么样'
  # test_open_router(content)

  test_get_transcribed_text(content)