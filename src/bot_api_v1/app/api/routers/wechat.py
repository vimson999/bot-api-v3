"""
微信小程序相关API路由

提供微信小程序登录、用户信息更新等接口
"""
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Body, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.core.schemas import BaseResponse
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.exceptions import CustomException
from bot_api_v1.app.db.session import get_db
from bot_api_v1.app.services.business.wechat_service import WechatService, WechatError
from bot_api_v1.app.services.business.points_service import PointsService, PointsError

from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig


router = APIRouter(prefix="/wechat", tags=["微信小程序"])


# 请求模型
class LoginRequest(BaseModel):
    """微信一站式登录请求模型"""
    code: str = Field(..., description="微信登录临时凭证")
    need_points: bool = Field(False, description="是否需要积分")
    userInfo: Optional[Dict[str, Any]] = Field(None, description="用户信息(昵称、头像等)")




class UserInfoRequest(BaseModel):
    """用户信息更新请求"""
    nickName: str = Field(..., description="用户昵称")
    avatarUrl: Optional[str] = Field(None, description="用户头像URL")
    gender: int = Field(0, description="用户性别: 0=未知, 1=男, 2=女")
    country: Optional[str] = Field(None, description="国家")
    province: Optional[str] = Field(None, description="省份")
    city: Optional[str] = Field(None, description="城市")
    language: Optional[str] = Field(None, description="语言")


class TokenRefreshRequest(BaseModel):
    """Token刷新请求"""
    token: str = Field(..., description="旧的JWT token")


# 实例化微信服务
wechat_service = WechatService()
points_service = PointsService()


# 定义依赖函数
async def verify_token(
    token: str = Header(..., description="JWT Token", alias="x-auth-token"),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    验证JWT Token并返回用户信息
    
    Args:
        token: JWT Token
        db: 数据库会话
    
    Returns:
        Dict: 包含user_id和openid的用户信息
    
    Raises:
        HTTPException: 验证失败时抛出401错误
    """
    try:
        return await wechat_service.verify_token(token, db)
    except WechatError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e)
        )


# API路由
@router.post(
    "/login",
    response_model=BaseResponse,
    description="微信小程序登录",
    summary="微信小程序登录"
)
@TollgateConfig(
    title="微信小程序登录",
    type="wechat_login",
    base_tollgate="20",
    current_tollgate="1",
    plat="wechat_mini"
)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    微信小程序登录
    
    接收微信小程序前端传来的临时登录凭证code，换取服务端JWT Token
    
    - 如果是新用户，会自动创建用户记录
    - 返回JWT Token，前端后续请求需要在Header中携带此Token
    """
    trace_key = request_ctx.get_trace_key()
    
    try:
        login_result = await wechat_service.login(login_data.code, db)
        
        user_id = login_result.get("user_id")
        is_new_user = login_result.get("is_new_user", False)
        
        # 2. 如果提供了用户信息，更新用户资料
        user_info = None
        if login_data.userInfo and user_id:
            try:
                user_info = await wechat_service.update_user_info(
                    user_id=user_id,
                    user_info=login_data.userInfo,
                    db=db
                )
                logger.info(
                    f"用户信息更新成功: {user_id}",
                    extra={"request_id": trace_key, "user_id": user_id}
                )
            except Exception as e:
                # 用户信息更新失败不影响登录流程
                logger.warning(
                    f"用户信息更新失败: {str(e)}",
                    extra={"request_id": trace_key, "user_id": user_id}
                )

        # 4. 获取用户积分信息
        points_info = {}
        try:
            if user_id:
                points_info = await points_service.get_user_points(user_id, db)
                logger.info(
                    f"用户积分获取成功: {user_id}",
                    extra={
                        "request_id": trace_key,
                        "user_id": user_id,
                        "available_points": points_info.get("available_points", 0)
                    }
                )
        except Exception as e:
            # 积分获取失败不影响登录流程
            logger.warning(
                f"用户积分获取失败: {str(e)}",
                extra={"request_id": trace_key, "user_id": user_id}
            )
            points_info = {
                "available_points": 0,
                "total_points": 0,
                "frozen_points": 0,
                "used_points": 0,
                "expired_points": 0
            }



        result = {
            "token": login_result.get("token"),
            "expires_in": login_result.get("expires_in"),
            "userInfo": user_info or {
                "user_id": user_id,
                "openid": login_result.get("openid"),
                "is_new_user": is_new_user
            },
            "points": {
                "available": points_info.get("available_points", 0),
                "total": points_info.get("total_points", 0),
                "frozen": points_info.get("frozen_points", 0),
                "used": points_info.get("used_points", 0),
                "expired": points_info.get("expired_points", 0),
                "expiring_soon": points_info.get("expiring_soon", [])
            }
        }

        
        logger.info(
            f"用户一站式登录成功: {user_id}",
            extra={
                "request_id": trace_key,
                "user_id": user_id,
                "is_new_user": is_new_user
            }
        )

        
        return BaseResponse(
            code=200,
            message="登录成功",
            data=result
        )
    except WechatError as e:
        logger.error(f"微信小程序登录失败: {str(e)}", 
                     extra={"request_id": trace_key})
        raise CustomException(
            status_code=401,
            message=f"登录失败: {str(e)}",
            code="wechat_login_error"
        )


@router.get(
    "/user/info",
    response_model=BaseResponse,
    description="更新用户信息",
    summary="更新微信用户信息"
)
@TollgateConfig(
    title="更新用户信息",
    type="wechat_user_info",
    base_tollgate="20",
    current_tollgate="1",
    plat="wechat_mini"
)
async def get_user_info(
    request: Request,
    token: str = Header(..., description="JWT Token", alias="Authorization"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前用户的基本信息和积分数据
    
    需要在Header中提供有效的JWT Token: Authorization: Bearer {token}
    
    返回用户基本信息(昵称、头像等)和积分数据
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
        
        # 2. 获取用户详细信息
        user_info = {}
        try:
            # 从数据库中获取用户的详细信息
            user = await wechat_service._get_user_by_id(user_id, db)
            if user:
                user_info = {
                    "user_id": str(user.id),
                    "nickname": user.nick_name,
                    "avatar": user.avatar,
                    "gender": user.gender,
                    "country": user.country,
                    "province": user.province,
                    "city": user.city,
                    "is_authorized": user.is_authorized
                }
            else:
                logger.warning(
                    f"找不到用户记录: {user_id}",
                    extra={"request_id": trace_key, "user_id": user_id}
                )
                # 提供基本信息
                user_info = {
                    "user_id": user_id,
                    "nickname": "微信用户",
                    "avatar": "",
                    "is_authorized": False
                }
        except Exception as e:
            logger.error(
                f"获取用户信息失败: {str(e)}",
                extra={"request_id": trace_key, "user_id": user_id},
                exc_info=True
            )
            # 提供基本信息不中断流程
            user_info = {
                "user_id": user_id,
                "nickname": "微信用户",
                "avatar": "",
                "is_authorized": False
            }
        
        # 3. 获取用户积分信息
        points_info = {}
        try:
            points_info = await points_service.get_user_points(user_id, db)
            logger.info(
                f"用户积分获取成功: {user_id}",
                extra={
                    "request_id": trace_key,
                    "user_id": user_id,
                    "available_points": points_info.get("available_points", 0)
                }
            )
        except Exception as e:
            logger.error(
                f"获取用户积分失败: {str(e)}",
                extra={"request_id": trace_key, "user_id": user_id},
                exc_info=True
            )
            # 提供默认积分信息不中断流程
            points_info = {
                "available_points": 0,
                "total_points": 0,
                "frozen_points": 0,
                "used_points": 0,
                "expired_points": 0,
                "expiring_soon": []
            }
        
        # 4. 构建返回结果
        result = {
            "userInfo": user_info,
            "points": {
                "available": points_info.get("available_points", 0),
                "total": points_info.get("total_points", 0),
                "frozen": points_info.get("frozen_points", 0),
                "used": points_info.get("used_points", 0),
                "expired": points_info.get("expired_points", 0),
                "expiring_soon": points_info.get("expiring_soon", [])
            }
        }
        
        logger.info(
            f"获取用户信息和积分成功: {user_id}",
            extra={"request_id": trace_key, "user_id": user_id}
        )
        
        return BaseResponse(
            code=200,
            message="获取用户信息成功",
            data=result
        )
        
    except WechatError as e:
        logger.error(
            f"微信Token验证失败: {str(e)}", 
            extra={"request_id": trace_key}
        )
        raise HTTPException(status_code=401, detail=f"Token验证失败: {str(e)}")
        
    except Exception as e:
        logger.error(
            f"获取用户信息时出现未知错误: {str(e)}", 
            exc_info=True, 
            extra={"request_id": trace_key}
        )
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.post(
    "/token/refresh",
    response_model=BaseResponse,
    description="刷新Token",
    summary="刷新微信登录Token"
)
@TollgateConfig(
    title="刷新Token",
    type="wechat_refresh_token",
    base_tollgate="20",
    current_tollgate="1",
    plat="wechat_mini"
)
async def refresh_token(
    request: Request,
    token_data: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    刷新JWT Token
    
    接收旧的JWT Token，返回新的Token
    
    - 即使旧Token已过期，仍然可以刷新
    - 但必须保证Token格式正确且用户存在
    """
    trace_key = request_ctx.get_trace_key()
    
    try:
        result = await wechat_service.refresh_token(token_data.token, db)
        
        return BaseResponse(
            code=200,
            message="Token刷新成功",
            data=result
        )
    except WechatError as e:
        logger.error(f"Token刷新失败: {str(e)}", 
                     extra={"request_id": trace_key})
        raise CustomException(
            status_code=401,
            message=f"Token刷新失败: {str(e)}",
            code="wechat_token_refresh_error"
        )