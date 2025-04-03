"""
微信公众号相关API路由

提供微信公众号用户关注、用户信息更新等接口
"""
from typing import Dict, Any, Optional
import json


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

from fastapi import Query, HTTPException
from fastapi.responses import PlainTextResponse
import hashlib
import xml.etree.ElementTree as ET
import urllib.parse

from fastapi.responses import RedirectResponse
from bot_api_v1.app.core.config import settings


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
    type="wechat_mp_callback",
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
            await wechat_service.handle_menu_click_event(event.EventKey, event.FromUserName,db)
            return PlainTextResponse(content="success")  
        else:
            logger.info(
                f"非关注事件，忽略处理: {event.Event}",
                extra={"request_id": trace_key, "openid": event.FromUserName}
            )
            return PlainTextResponse(content="success")  
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
    type="wechat_mp_prodcut_list",
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
        
        if not openid:
            logger.error("获取用户openid失败")
            # 重定向到错误页面
            return RedirectResponse(url=f"/static/error.html?code=401&message={urllib.parse.quote('授权失败')}")
        
        # 2. 生成JWT令牌，包含用户身份信息
        token = await wechat_service.generate_h5_token(openid)
        
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



# ... 现有代码 ...


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
            "product_name": order_info.product_snapshot.get("name", "未知商品") if order_info.product_snapshot else "未知商品",
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