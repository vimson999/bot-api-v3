"""
微信公众号相关API路由

提供微信公众号用户关注、用户信息更新等接口
"""
from typing import Dict, Any, Optional
import json
import os


from bot_api_v1.app.services.business.user_service import UserService
from bot_api_v1.app.services.business.order_service import OrderService, OrderError
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.exceptions import CustomException
from bot_api_v1.app.db.session import get_db
from bot_api_v1.app.services.business.wechat_service import WechatService, WechatError
from bot_api_v1.app.services.business.product_service import ProductService

from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
import hashlib
import xml.etree.ElementTree as ET
import urllib.parse

from fastapi.responses import RedirectResponse
from bot_api_v1.app.core.config import settings


# --- 新增：微信加密相关 ---
from wechatpy.crypto import WeChatCrypto
from wechatpy.utils import check_signature # 用于GET请求验证

try:
    crypt_handler = WeChatCrypto(settings.WECHAT_MP_TOKEN, settings.WECHAT_MP_ENCODINGAESKEY, settings.WECHAT_MP_APPID)
except Exception as e:
    logger.error(f"初始化微信加密处理器失败: {e}")
    crypt_handler = None # 应该阻止应用启动或妥善处理

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
user_service = UserService()
@router.post(
    "/callback",
    response_model=BaseResponse,
    description="微信公众号回调接口",
    summary="处理微信公众号事件"
)
@TollgateConfig(
    title="微信公众号回调",
    type="wechat_mp_callback",
    base_tollgate="20",
    current_tollgate="1",
    plat="wechat_mp"
)
async def wechat_mp_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    msg_signature: str = Query(..., description="微信加密签名"), # 从查询参数获取
    timestamp: str = Query(..., description="时间戳"),         # 从查询参数获取
    nonce: str = Query(..., description="随机数")             # 从查询参数获取
):
    """
    处理微信公众号事件回调
    """
    trace_key = request_ctx.get_trace_key()
    
    if not crypt_handler:
        logger.error("微信加密处理器未初始化，无法处理回调", extra={"request_id": trace_key})
        # 根据微信要求，即使处理失败也应尽量返回"success"或空字符串，避免微信重试轰炸
        # 但这里是严重配置问题，也可以考虑返回500错误
        return PlainTextResponse(content="success") # 或者抛出内部错误

    try:
        # 1. 读取加密的请求体
        encrypted_xml_data = await request.body()

        # 2. 解密消息
        try:
            decrypted_xml = crypt_handler.decrypt_message(
                msg=encrypted_xml_data.decode('utf-8'), # wechatpy 需要 str 类型
                signature=msg_signature,
                timestamp=timestamp,
                nonce=nonce
            )
        except (InvalidSignatureException, InvalidAppIdException) as crypto_err:
            logger.error(
                f"微信消息解密或签名验证失败: {crypto_err}",
                extra={
                    "request_id": trace_key,
                    "msg_signature": msg_signature,
                    "timestamp": timestamp,
                    "nonce": nonce
                }
            )
            # 微信建议即使解密失败也返回空字符串或"success"
            # 也可以选择抛出HTTP 403/400，但要注意微信的重试机制
            # 此处为了调试和明确问题，暂时返回错误，实际部署时可能需要调整
            raise CustomException(
                status_code=400, # 或403
                message=f"消息解密或签名验证失败: {crypto_err}",
                code="decryption_or_signature_failed"
            )

        # Read and parse XML data
        # xml_data = await request.body()
        # root = ET.fromstring(xml_data)
        # event_data = {child.tag: child.text for child in root}

        root = ET.fromstring(decrypted_xml)
        event_data = {child.tag: child.text for child in root}
        logger.info(f"解密后的事件数据: {event_data}", extra={"request_id": trace_key})


        # Check required fields before model validation
        required_fields = ["ToUserName", "FromUserName", "CreateTime", "MsgType", "Event"]
        missing_fields = [field for field in required_fields if field not in event_data]
        if missing_fields:
            logger.error(
                f"Missing required fields in WechatMpEvent: {missing_fields}",
                extra={"request_id": trace_key, "event_data": event_data}
            )
            raise CustomException(
                status_code=400,
                message=f"Missing required fields: {', '.join(missing_fields)}",
                code="missing_fields"
            )

        # Convert to WechatMpEvent model
        event = WechatMpEvent(**event_data)
        
        # 设置请求上下文信息
        client_ip = request.client.host if request.client else None

        ctx = request_ctx.get_context()
        ctx.update({
            'source': 'wechat_mp',  # 来源为微信公众号
            'user_id': event.FromUserName,  # OpenID作为用户ID
            'user_name': None,  # 此时还未获取用户昵称
            'app_id': event.ToUserName,  # 公众号的原始ID
            'ip_address': client_ip,  # XML请求中没有IP信息
        })
        request_ctx.set_context(ctx)

        # 只处理关注事件
        if event.Event.lower() == "subscribe":
            # 获取用户OpenID并处理关注事件
            result = await wechat_service.handle_user_subscribe(
                event.FromUserName, 
                trace_key, 
                db
            )
            
            return PlainTextResponse(content="success")  
        elif event.Event.lower() == "click":
            # 确保 EventKey 不为 None 再传入
            if event.EventKey:
                await wechat_service.handle_menu_click_event(event.EventKey, event.FromUserName, db)
            else:
                logger.warning(
                    "菜单点击事件 EventKey 为空",
                    extra={"openid": event.FromUserName}
                )
            return PlainTextResponse(content="success")  
        else:
            logger.info(
                f"非关注事件，忽略处理: {event.Event}",
                extra={"request_id": trace_key, "openid": event.FromUserName}
            )
            return PlainTextResponse(content="success")  
    except CustomException as ce:
        # Log and re-raise known custom exceptions
        logger.error(
            f"处理微信公众号事件时发生已知错误: {ce.message}", 
            exc_info=True,
            extra={"request_id": trace_key}
        )
        raise ce
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



@router.get("/product/list")
@TollgateConfig(
    title="展示商品",
    type="wechat_mp_product_list",
    base_tollgate="20",
    current_tollgate="1",
    plat="wechat_mp"
)
async def handle_product_list(
    code: str = Query(..., description="微信授权code"),
    state: str = Query(..., description="自定义state参数"),
    db: AsyncSession = Depends(get_db)
):
    """
    处理微信授权后的商品列表请求
    
    流程：
    1. 通过code获取用户openid
    2. 生成令牌
    3. 重定向到静态HTML页面
    """
    try:        
        # 1. 通过code获取access_token和openid
        user_info = await wechat_service.get_mp_user_info_from_code_h5(code)
        openid = user_info.get('openid')

        # 2. 生成令牌
        if not openid:
            logger.error("获取用户openid失败")
            # 重定向到错误页面
            return RedirectResponse(url=f"/static/error.html?code=401&message={urllib.parse.quote('授权失败')}")
        

        trace_key = request_ctx.get_trace_key()
        #3 根据openid获取用户信息
        user_id = await user_service.get_user_id_by_openid(db, openid,"wx",trace_key)
        if not user_id:
            logger.error("获取用户信息失败")
            # 重定向到错误页面
            return RedirectResponse(url=f"/static/error.html?code=401&message={urllib.parse.quote('授权失败')}")
        user_id_str = str(user_id)

        # 2. 生成JWT令牌，包含用户身份信息
        token = await wechat_service.generate_h5_token(user_id_str,openid)
        
        # 3. 重定向到静态HTML页面
        return RedirectResponse(url=f"/static/product_list.html?token={token}&openid={openid}")
    except WechatError as e:
        logger.error(f"微信授权处理失败: {str(e)}")
        return RedirectResponse(url=f"/static/error.html?code=400&message={urllib.parse.quote(str(e))}")
    except Exception as e:
        logger.error(f"处理商品列表请求失败: {str(e)}", exc_info=True)
        return RedirectResponse(url=f"/static/error.html?code=500&message={urllib.parse.quote('服务异常')}")

# 添加API端点提供商品数据
@router.get("/products", response_model=Dict[str, Any])
async def get_products(
    token: str = Query(..., description="用户令牌"),
    db: AsyncSession = Depends(get_db)
):
    """获取商品列表数据API"""
    try:
        # 验证令牌
        # wechat_service = WechatService()
        # openid = await wechat_service.verify_h5_token(token)
        
        # if not openid:
        #     raise HTTPException(status_code=401, detail="无效的令牌")
        
        # # 获取用户信息
        # user_info = await wechat_service._get_mp_user_info_from_wechat(openid)
        
        # 获取商品列表
        product_service = ProductService()
        products = await product_service.get_product_list(db)
        
        return {
            # "user_info": user_info,
            "products": products
        }
    except Exception as e:
        logger.error(f"获取商品列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="服务异常")



# 添加创建订单的请求模型
class CreateOrderRequest(BaseModel):
    product_id: str = Field(..., description="商品ID")
    token: str = Field(..., description="用户令牌")
    openid: Optional[str] = Field(None, description="用户OpenID")

order_service = OrderService()
@router.post(
    "/create_order",
    response_model=BaseResponse,
    description="创建微信支付订单",
    summary="创建微信支付订单"
)
@TollgateConfig(
    title="创建微信支付订单",
    type="wechat_mp_create_order",
    base_tollgate="20",
    current_tollgate="1",
    plat="wechat_mp"
)
async def create_order(
    request: CreateOrderRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    创建微信支付订单
    """
    trace_key = request_ctx.get_trace_key()
    
    try:
        # 验证token
        user_info = await wechat_service.verify_token(request.token, db)
        
        # 获取商品信息
        product_service = ProductService()
        product = await product_service.get_product_by_id(request.product_id, db)
        if not product:
            return BaseResponse(
                code=404,
                message="商品不存在",
                data=None
            )
        
        # 使用OrderService创建订单
        order_data = await order_service.create_order(
            user_id=user_info["user_id"],
            openid=user_info["openid"],
            product_id=request.product_id,
            product_name=product.name,
            amount=product.sale_price,
            total_points=product.point_amount,
            db=db
        )
        
        return BaseResponse(
            code=0,
            message="订单创建成功",
            data={"order_id": order_data["order_id"]}
        )
        
    except Exception as e:
        logger.error(
            f"创建订单失败: {str(e)}",
            exc_info=True,
            extra={"request_id": trace_key}
        )
        return BaseResponse(
            code=500,
            message=f"创建订单失败: {str(e)}",
            data=None
        )

@router.get(
    "/pay",
    description="微信支付页面",
    summary="微信支付页面"
)
@TollgateConfig(
    title="微信支付页面",
    type="wechat_mp_pay_order",
    base_tollgate="20",
    current_tollgate="1",
    plat="wechat_mp"
)
async def payment_page(
    order_id: str = Query(..., description="订单ID"),
    token: str = Query(..., description="用户令牌"),
    db: AsyncSession = Depends(get_db)
):
    """
    微信支付页面
    """
    trace_key = request_ctx.get_trace_key()
    
    try:
        # 验证token
        user_info = await wechat_service.verify_token(token, db)
        
        # 使用OrderService获取订单信息
        order_info = await order_service.get_order_info(order_id, db)
        
        if not order_info:
            raise HTTPException(status_code=404, detail="订单不存在")
        
        # 检查订单是否属于当前用户
        if str(order_info.user_id) != user_info["user_id"]:
            raise HTTPException(status_code=403, detail="无权访问此订单")
        
        # 创建微信支付参数
        pay_params = await wechat_service.create_jsapi_payment(
            order_id=order_id,
            openid=user_info["openid"],
            product_name=order_info.product_name,  # 直接访问属性而不是使用get方法
            total_fee=float(order_info.total_amount),  # 添加订单金额参数
            db=db
        )
        
        # 返回支付页面
        return RedirectResponse(
            url=f"/static/html/payment.html?order_id={order_id}&token={token}&pay_params={urllib.parse.quote(json.dumps(pay_params))}"
        )
        
    except Exception as e:
        logger.error(
            f"获取支付页面失败: {str(e)}",
            exc_info=True,
            extra={"request_id": trace_key}
        )
        return RedirectResponse(url=f"/static/html/error.html?message=支付页面加载失败")


@router.get(
    "/order_detail",
    response_model=BaseResponse,
    description="获取订单详情",
    summary="获取订单详情"
)
async def get_order_detail(
    order_id: str = Query(..., description="订单ID"),
    token: str = Query(..., description="用户令牌"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取订单详情
    """
    trace_key = request_ctx.get_trace_key()
    
    try:
        # 验证token
        user_info = await wechat_service.verify_token(token, db)
        
        # 使用OrderService获取订单信息
        order_info = await order_service.get_order_info(order_id, db)
        
        if not order_info:
            return BaseResponse(
                code=404,
                message="订单不存在",
                data=None
            )
        
        # 检查订单是否属于当前用户
        if str(order_info.user_id) != user_info["user_id"]:
            return BaseResponse(
                code=403,
                message="无权访问此订单",
                data=None
            )
        
        # 构建订单详情
        order_detail = {
            "order_id": str(order_info.id),
            "order_no": order_info.order_no,
            "amount": float(order_info.total_amount),
            "status": order_info.order_status,
            "product_name": str(order_info.product_name),
            # "product_name": order_info.product_snapshot.get("name", "未知商品") if order_info.product_snapshot else "未知商品",
            "created_at": order_info.created_at.isoformat() if order_info.created_at else None
        }
        
        return BaseResponse(
            code=0,
            message="获取订单详情成功",
            data=order_detail
        )
        
    except Exception as e:
        logger.error(
            f"获取订单详情失败: {str(e)}",
            exc_info=True,
            extra={"request_id": trace_key}
        )
        return BaseResponse(
            code=500,
            message=f"获取订单详情失败: {str(e)}",
            data=None
        )







@router.post(
    "/update_menu",
    response_model=BaseResponse,
    description="更新微信公众号菜单",
    summary="更新微信公众号菜单"
)
@TollgateConfig(
    title="更新微信公众号菜单",
    type="trigger_wechat_menu_update",
    base_tollgate="20",
    current_tollgate="1",
    plat="wechat_mp"
)
async def trigger_wechat_menu_update(
    request: Request
):
    """
    更新微信公众号菜单
    """
    trace_key = request_ctx.get_trace_key()
    
    try:
        if settings.CURRENT_WECHAT_MP_MENU_VERSION < settings.TARGET_WECHAT_MP_MENU_VERSION:
            access_token = await wechat_service._get_mp_access_token()
            await wechat_service.create_wechat_menu(access_token)
            
            # 直接更新设置值
            settings.CURRENT_WECHAT_MP_MENU_VERSION = settings.TARGET_WECHAT_MP_MENU_VERSION
            
            logger.info_to_db(f"成功创建微信公众号菜单,微信菜单已更新到版本 {settings.TARGET_WECHAT_MP_MENU_VERSION}")
            return BaseResponse(
                code=0,
                message="菜单更新成功",
                data=None
            )
        else:
            return BaseResponse(
                code=0,
                message="菜单已是最新版本",
                data=None
            )
    except Exception as e:
        logger.error(
            f"菜单更新失败 : {str(e)}",
            exc_info=True,
            extra={"request_id": trace_key}
        )
        return BaseResponse(
            code=500,
            message=f"菜单更新失败: {str(e)}",
            data=None
        )

### 2. 微信支付结果通知 `/api/wechat_mp/payment/notify`

@router.post(
    "/payment/notify",
    description="微信支付结果通知",
    summary="微信支付异步通知"
)
async def payment_notify(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    微信支付结果异步通知
    """
    try:
        xml_data = await request.body()
        root = ET.fromstring(xml_data)
        notify_data = {child.tag: child.text for child in root}
        logger.info_to_db(f"payment---notify---收到微信支付通知: {notify_data}")

        # 校验签名（可选，建议实现）
        # sign = notify_data.get("sign")
        # ...签名校验逻辑...

        # 处理支付结果
        if notify_data.get("return_code") == "SUCCESS" and notify_data.get("result_code") == "SUCCESS":
            out_trade_no = notify_data.get("out_trade_no")
            # 更新订单状态为已支付
            await order_service.update_order_status_by_no(out_trade_no, 2, db=db)  # 2=已支付
            logger.info(f"订单{out_trade_no}支付成功，已更新状态")
            # 返回微信要求的XML
            return PlainTextResponse(
                content="<xml><return_code><![CDATA[SUCCESS]]></return_code><return_msg><![CDATA[OK]]></return_msg></xml>",
                media_type="application/xml"
            )
        else:
            logger.warning(f"支付失败或异常: {notify_data}")
            return PlainTextResponse(
                content="<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[支付失败]]></return_msg></xml>",
                media_type="application/xml"
            )
    except Exception as e:
        logger.error(f"处理微信支付通知失败: {str(e)}")
        return PlainTextResponse(
            content="<xml><return_code><![CDATA[FAIL]]></return_code><return_msg><![CDATA[服务器异常]]></return_msg></xml>",
            media_type="application/xml"
        )



@router.get(
    "/pay_success",
    description="支付成功页面跳转",
    summary="支付成功页面"
)
@TollgateConfig(
    title="支付成功页面",
    type="wechat_mp_pay_success",
    base_tollgate="20",
    current_tollgate="1",
    plat="wechat_mp"
)
async def pay_success(
    order_id: str = Query(..., description="订单ID"),
    token: str = Query(..., description="用户令牌"),
    db: AsyncSession = Depends(get_db)
):
    """
    支付成功页面跳转
    """
    try:
        # 可选：校验token和订单归属
        user_info = await wechat_service.verify_token(token, db)
        order_info = await order_service.get_order_info(order_id, db)
        if not order_info or str(order_info.user_id) != user_info["user_id"]:
            return RedirectResponse(url=f"/static/html/error.html?message=订单不存在或无权访问")
        # 跳转到支付成功静态页面
        return RedirectResponse(url=f"/static/html/pay_success.html?order_id={order_id}")
    except Exception as e:
        logger.error(f"支付成功跳转失败: {str(e)}")
        return RedirectResponse(url=f"/static/html/error.html?message=支付成功页面加载失败")

