"""
微信公众号相关API路由

提供微信公众号用户关注、用户信息更新等接口
"""
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.exceptions import CustomException
from bot_api_v1.app.db.session import get_db
from bot_api_v1.app.services.business.wechat_service import WechatService, WechatError
from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig

from fastapi import Query, HTTPException
from fastapi.responses import PlainTextResponse
import hashlib
import xml.etree.ElementTree as ET

router = APIRouter(prefix='/wechat_mp',  tags=["微信公众号"])


# 请求模型
class WechatMpEvent(BaseModel):
    """微信公众号事件请求模型"""
    ToUserName: str = Field(..., description="开发者微信号")
    FromUserName: str = Field(..., description="发送方帐号（一个OpenID）")
    CreateTime: int = Field(..., description="消息创建时间（整型）")
    MsgType: str = Field(..., description="消息类型，event")
    Event: str = Field(..., description="事件类型，subscribe(订阅)、unsubscribe(取消订阅)")
    EventKey: Optional[str] = Field(None, description="事件KEY值，qrscene_为前缀，后面为二维码的参数值")


# 实例化微信服务
wechat_service = WechatService()

@router.post(
    "/callback",
    response_model=BaseResponse,
    description="微信公众号回调接口",
    summary="处理微信公众号事件"
)
@TollgateConfig(
    title="微信公众号回调",
    type="subscribe",
    base_tollgate="20",
    current_tollgate="1",
    plat="wechat_mp"
)
async def wechat_mp_callback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    处理微信公众号事件回调
    """
    trace_key = request_ctx.get_trace_key()
    
    try:
        # Read and parse XML data
        xml_data = await request.body()
        root = ET.fromstring(xml_data)
        event_data = {child.tag: child.text for child in root}
        
        # Convert to WechatMpEvent model
        event = WechatMpEvent(**event_data)
        
        # 只处理关注事件
        if event.Event.lower() == "subscribe":
            # 获取用户OpenID并处理关注事件
            result = await wechat_service.handle_user_subscribe(
                event.FromUserName, 
                trace_key, 
                db
            )
            
            return BaseResponse(
                code=200,
                message="用户关注处理成功",
                data=result
            )
        elif event.Event.lower() == "click":
            await wechat_service.handle_menu_click_event(event.EventKey, event.FromUserName, access_token)
            return BaseResponse(code=200, message="菜单点击事件处理成功")
        else:
            logger.info(
                f"非关注事件，忽略处理: {event.Event}",
                extra={"request_id": trace_key, "openid": event.FromUserName}
            )
            return BaseResponse(
                code=200,
                message="事件已接收",
                data={"event": event.Event}
            )
    except Exception as e:
        logger.error(
            f"处理微信公众号事件时发生未知错误: {str(e)}", 
            exc_info=True,
            extra={"request_id": trace_key}
        )
        raise CustomException(
            status_code=500,
            message="服务器内部错误",
            code="internal_server_error"
        )

@router.get(
    "/callback",
    description="微信公众号服务器验证接口",
    summary="验证微信公众号服务器配置"
)
async def verify_wechat_mp(
    request: Request,
    signature: str,
    timestamp: str,
    nonce: str,
    echostr: str
):
    """
    验证微信公众号服务器配置
    
    微信公众号配置服务器URL时，微信服务器会发送GET请求进行验证
    
    - 验证通过后返回echostr参数内容
    - 验证失败返回错误信息
    """
    trace_key = request_ctx.get_trace_key()
    
    try:
        # 验证签名
        is_valid = await wechat_service.verify_mp_signature(signature, timestamp, nonce)
        
        if is_valid:
            logger.info(
                "微信公众号服务器验证成功",
                extra={"request_id": trace_key}
            )
            # 验证成功，返回echostr
            return PlainTextResponse(content=echostr)
        else:
            logger.warning(
                "微信公众号服务器验证失败: 签名不匹配",
                extra={
                    "request_id": trace_key,
                    "signature": signature,
                    "timestamp": timestamp,
                    "nonce": nonce
                }
            )
            raise HTTPException(status_code=403, detail="签名验证失败")
    except Exception as e:
        logger.error(
            f"微信公众号服务器验证出错: {str(e)}",
            exc_info=True,
            extra={"request_id": trace_key}
        )
        raise HTTPException(status_code=500, detail="服务器内部错误")















# def check_signature(token: str, signature: str, timestamp: str, nonce: str) -> bool:
#     """
#     Verify the signature from WeChat server
    
#     Args:
#         token (str): Token configured in WeChat official account settings
#         signature (str): Signature from WeChat server
#         timestamp (str): Timestamp from WeChat server
#         nonce (str): Random number from WeChat server
    
#     Returns:
#         bool: Whether the signature is valid
#     """
#     # 1. Create a list with token, timestamp, and nonce
#     tmp_list = [token, timestamp, nonce]
    
#     # 2. Sort the list
#     tmp_list.sort()
    
#     # 3. Join the sorted list into a single string
#     tmp_str = ''.join(tmp_list)
    
#     # 4. SHA1 hash the string
#     sha1_str = hashlib.sha1(tmp_str.encode('utf-8')).hexdigest()
    
#     # 5. Compare the hashed string with the signature
#     return sha1_str == signature


# @router.get("/wx")
# async def wechat_verify(
#     signature: str = Query(..., description="微信加密签名"),
#     timestamp: str = Query(..., description="时间戳"),
#     nonce: str = Query(..., description="随机数"),
#     echostr: str = Query(..., description="随机字符串")
# ):
#     """
#     微信公众号服务器配置验证接口
    
#     处理微信服务器发来的验证请求，验证服务器配置的有效性
    
#     Args:
#         signature: 微信加密签名
#         timestamp: 时间戳
#         nonce: 随机数
#         echostr: 验证成功后需要返回的随机字符串
    
#     Returns:
#         成功返回echostr，失败返回错误信息
#     """
#     try:
#         # 获取配置的token
#         token = settings.WECHAT_MP_TOKEN
        
#         if not token:
#             logger.error("未配置微信公众号Token")
#             raise HTTPException(
#                 status_code=500, 
#                 detail="未配置微信公众号Token"
#             )

#         # 读取原始XML数据
#         xml_data = await request.body()
        
#         # 验证签名
#         if check_signature(token, signature, timestamp, nonce):
#             logger.info("微信公众号服务器验证成功")
#             return PlainTextResponse(content=echostr)
#         else:
#             logger.warning(
#                 "微信公众号签名验证失败",
#                 extra={
#                     "signature": signature,
#                     "timestamp": timestamp,
#                     "nonce": nonce
#                 }
#             )
#             raise HTTPException(
#                 status_code=403, 
#                 detail="签名验证失败"
#             )
            
#     except Exception as e:
#         logger.error(f"处理微信验证请求时出错: {str(e)}", exc_info=True)
#         raise HTTPException(
#             status_code=500,
#             detail=f"服务器内部错误: {str(e)}"
#         )




# @router.post("/wx")
# async def handle_wechat_message(
#     request: Request,
#     wechat_service: WechatService = Depends(WechatService)
# ):
#     """
#     Handle incoming messages from WeChat server
#     """
#     # 读取原始XML数据
#     xml_data = await request.body()
    
#     try:
#         # 解析XML消息
#         msg = parse_xml(xml_data)
        
#         # 处理订阅事件
#         if msg.get('MsgType') == 'event' and msg.get('Event') == 'subscribe':
#             # 获取用户的OpenID
#             open_id = msg['FromUserName']
            
#             # 获取Access Token
#             access_token = await wechat_service._get_mp_access_token()
#             if access_token:
#                 # 发送模板消息
#                 send_template_message(access_token, open_id)
            
#             # 回复文本消息
#             welcome_msg = "感谢关注！我们将为您提供最佳服务。回复以下关键词获取更多信息：\n1. 帮助\n2. 服务\n3. 优惠"
#             return Response(content=generate_text_response_xml(msg, welcome_msg), media_type="application/xml")
        
#         # 处理其他类型的消息
#         return Response(content="success", media_type="text/plain")
    
#     except Exception as e:
#         print(f"Error processing message: {e}")
#         return Response(content="error", media_type="text/plain")



# def parse_xml(xml_data: bytes) -> Dict[str, str]:
#     """
#     Parse XML message from WeChat
#     """
#     root = ET.fromstring(xml_data)
#     return {child.tag: child.text for child in root}



# def generate_text_response_xml(msg: Dict[str, str], content: str) -> str:
#     """
#     Generate XML response for text message
#     """
#     return f"""
# <xml>
#     <ToUserName><![CDATA[{msg['FromUserName']}]]></ToUserName>
#     <FromUserName><![CDATA[{msg['ToUserName']}]]></FromUserName>
#     <CreateTime>{int(time.time())}</CreateTime>
#     <MsgType><![CDATA[text]]></MsgType>
#     <Content><![CDATA[{content}]]></Content>
# </xml>
# """



# def send_template_message(access_token: str, open_id: str, template_id: Optional[str] = '0QbSRPz7YAIWxtgcNmC4SxrEEXlpOyji33zkKDQ6Xnc'):
#     """
#     Send template message to new subscriber
#     """
#     url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"
    
#     # 模板消息数据
#     template_data = {
#         "touser": open_id,
#         "template_id": template_id,  # 在微信公众号后台配置的模板ID
#         # "url": "https://yourwebsite.com",  # 可选的跳转链接
#         "data": {
#             "userName": {
#                 "value": "欢迎关注我们！",
#                 "color": "#173177"
#             }
#         }
#     }
    
#     try:
#         response = requests.post(url, json=template_data)
#         return response.json()
#     except Exception as e:
#         print(f"Error sending template message: {e}")
#         return None