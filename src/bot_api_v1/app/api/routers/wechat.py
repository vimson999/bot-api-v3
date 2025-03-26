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
from bot_api_v1.app.utils.decorators.tollgate import TollgateConfig


router = APIRouter(prefix="/wechat", tags=["微信小程序"])


# 请求模型
class LoginRequest(BaseModel):
    """微信小程序登录请求"""
    code: str = Field(..., description="微信登录临时凭证")


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
        result = await wechat_service.login(login_data.code, db)
        
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


@router.post(
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
async def update_user_info(
    request: Request,
    user_info: UserInfoRequest,
    user_data: Dict[str, Any] = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """
    更新微信用户信息
    
    接收微信小程序前端传来的用户信息，更新到服务端用户记录
    
    - 需要在Header中携带有效的JWT Token
    - 用户信息来自微信开放数据
    """
    trace_key = request_ctx.get_trace_key()
    user_id = user_data.get("user_id")
    
    try:
        result = await wechat_service.update_user_info(
            user_id, 
            user_info.dict(exclude_unset=True),
            db
        )
        
        return BaseResponse(
            code=200,
            message="用户信息更新成功",
            data=result
        )
    except WechatError as e:
        logger.error(f"更新用户信息失败: {str(e)}", 
                     extra={"request_id": trace_key})
        raise CustomException(
            status_code=400,
            message=f"更新用户信息失败: {str(e)}",
            code="wechat_user_update_error"
        )


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