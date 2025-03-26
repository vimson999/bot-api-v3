"""
微信小程序积分API路由模块

提供获取、消费和管理用户积分的API端点。
"""
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Header, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig
from bot_api_v1.app.services.business.wechat_service import WechatService, WechatError
from bot_api_v1.app.services.business.points_service import PointsService, PointsError
from bot_api_v1.app.db.session import get_db


router = APIRouter(prefix="/points", tags=["用户积分"])

# 实例化服务
wechat_service = WechatService()
points_service = PointsService()


@router.get(
    "/balance",
    response_model=BaseResponse,
    description="获取用户积分余额",
    summary="获取当前用户的积分余额"
)
@TollgateConfig(
    title="获取积分余额",
    type="points_balance",
    base_tollgate="30",
    current_tollgate="1",
    plat="wechat_mini"
)
async def get_points_balance(
    request: Request,
    token: str = Header(..., description="JWT Token", alias="Authorization"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前用户的积分余额
    
    需要在Header中提供有效的JWT Token: Authorization: Bearer {token}
    
    返回积分余额、已用积分、冻结积分等信息
    """
    trace_key = request_ctx.get_trace_key()
    
    # 处理Bearer token格式
    if token.startswith("Bearer "):
        token = token[7:]
    
    try:
        # 1. 验证Token并获取用户信息
        user_data = await wechat_service.verify_token(token, db)
        user_id = user_data.get("user_id")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="无效的用户Token")
        
        # 2. 获取用户积分信息
        points_info = await points_service.get_user_points(user_id, db)
        
        # 3. 构建返回结果
        result = {
            "balance": {
                "total_points": points_info.get("total_points", 0),
                "available_points": points_info.get("available_points", 0),
                "frozen_points": points_info.get("frozen_points", 0),
                "used_points": points_info.get("used_points", 0),
                "expired_points": points_info.get("expired_points", 0)
            },
            "last_update": points_info.get("last_update", None),
            "expiring_soon": points_info.get("expiring_soon", []),
            "user_id": user_id
        }
        
        logger.info(
            f"用户积分查询成功: {user_id}",
            extra={
                "request_id": trace_key,
                "user_id": user_id,
                "available_points": points_info.get("available_points", 0)
            }
        )
        
        return BaseResponse(
            code=200,
            message="积分查询成功",
            data=result
        )
        
    except WechatError as e:
        logger.error(
            f"微信Token验证失败: {str(e)}", 
            extra={"request_id": trace_key}
        )
        raise HTTPException(status_code=401, detail=f"Token验证失败: {str(e)}")
        
    except PointsError as e:
        logger.error(
            f"获取用户积分失败: {str(e)}", 
            extra={"request_id": trace_key}
        )
        raise HTTPException(status_code=400, detail=f"获取积分失败: {str(e)}")
        
    except Exception as e:
        logger.error(
            f"处理积分请求时出现未知错误: {str(e)}", 
            exc_info=True, 
            extra={"request_id": trace_key}
        )
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.get(
    "/history",
    response_model=BaseResponse,
    description="获取用户积分历史记录",
    summary="获取用户积分交易历史"
)
@TollgateConfig(
    title="积分历史记录",
    type="points_history",
    base_tollgate="30",
    current_tollgate="1",
    plat="wechat_mini"
)
async def get_points_history(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=50, description="每页记录数"),
    transaction_type: Optional[str] = Query(None, description="交易类型: PURCHASE,CONSUME,EXPIRE,ADJUST,REFUND"),
    token: str = Header(..., description="JWT Token", alias="Authorization"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户积分交易历史记录
    
    需要在Header中提供有效的JWT Token: Authorization: Bearer {token}
    
    可以筛选指定类型的交易记录:
    - PURCHASE: 购买获得
    - CONSUME: 消费使用
    - EXPIRE: 积分过期
    - ADJUST: 人工调整
    - REFUND: 退款返还
    
    分页参数:
    - page: 页码，从1开始
    - page_size: 每页记录数
    """
    trace_key = request_ctx.get_trace_key()
    
    # 处理Bearer token格式
    if token.startswith("Bearer "):
        token = token[7:]
    
    try:
        # 1. 验证Token并获取用户信息
        user_data = await wechat_service.verify_token(token, db)
        user_id = user_data.get("user_id")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="无效的用户Token")
        
        # 2. 获取用户积分历史记录
        history_data = await points_service.get_points_history(
            user_id=user_id,
            transaction_type=transaction_type,
            page=page,
            page_size=page_size,
            db=db
        )
        
        logger.info(
            f"查询用户积分历史成功: {user_id}",
            extra={
                "request_id": trace_key,
                "user_id": user_id,
                "page": page,
                "page_size": page_size
            }
        )
        
        return BaseResponse(
            code=200,
            message="积分历史查询成功",
            data=history_data
        )
        
    except WechatError as e:
        logger.error(
            f"微信Token验证失败: {str(e)}", 
            extra={"request_id": trace_key}
        )
        raise HTTPException(status_code=401, detail=f"Token验证失败: {str(e)}")
        
    except PointsError as e:
        logger.error(
            f"获取用户积分历史失败: {str(e)}", 
            extra={"request_id": trace_key}
        )
        raise HTTPException(status_code=400, detail=f"获取积分历史失败: {str(e)}")
        
    except Exception as e:
        logger.error(
            f"处理积分历史请求时出现未知错误: {str(e)}", 
            exc_info=True, 
            extra={"request_id": trace_key}
        )
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")