"""
微信小程序服务模块

提供微信小程序登录、用户信息解密等功能。
"""
import json
import time
import uuid
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

import httpx
import jwt
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.cache import cache_result
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
from bot_api_v1.app.models.meta_user import MetaUser, PlatformScopeEnum
from bot_api_v1.app.constants.log_types import LogEventType, LogSource
from bot_api_v1.app.core.config import settings


class WechatError(Exception):
    """微信服务操作过程中出现的错误"""
    pass


class WechatService:
    """微信小程序服务，提供微信登录、用户信息等功能"""
    
    def __init__(self):
        """初始化微信服务"""
        self.appid = settings.WECHAT_MINI_APPID
        self.secret = settings.WECHAT_MINI_SECRET
        self.token_secret = settings.JWT_SECRET_KEY
        self.token_algorithm = "HS256"
        self.token_expires = 7  # 7天
    
    @gate_keeper()
    @log_service_call(method_type="wechat", tollgate="20-2")
    async def login(self, code: str, db: AsyncSession) -> Dict[str, Any]:
        """
        微信小程序登录
        
        Args:
            code: 微信登录临时凭证
            db: 数据库会话
            
        Returns:
            Dict: 包含 token, openid 和 is_new_user 标志
            
        Raises:
            WechatError: 登录过程中的错误
        """
        # 获取 trace_key 用于日志
        trace_key = request_ctx.get_trace_key()
        logger.info(f"正在处理微信小程序登录请求，code={code[:4]}...", 
                    extra={"request_id": trace_key})
        
        try:
            # 1. 通过 code 获取 openid 和 session_key
            openid, session_key = await self._code2session(code)
            if not openid:
                raise WechatError("获取 openid 失败")
            
            # 2. 查询或创建用户
            user, is_new_user = await self._get_or_create_user(db, openid)
            if not user:
                raise WechatError("用户记录处理失败")
            
            # 3. 生成 JWT token
            token = self._generate_token(user.id, openid)
            
            # 4. 更新用户登录信息
            await self._update_user_login_info(db, user, is_new_user)
            
            # 5. 构建返回结果
            result = {
                "token": token,
                "openid": openid,
                "is_new_user": is_new_user,
                "user_id": str(user.id),
                "expires_in": self.token_expires * 86400  # 秒为单位
            }
            
            # 6. 记录详细日志
            log_type = LogEventType.USER_REGISTER_LOGIN if is_new_user else LogEventType.USER_LOGIN
            logger.info(
                f"微信小程序用户{'注册并' if is_new_user else ''}登录成功: {openid}",
                extra={
                    "request_id": trace_key,
                    "user_id": str(user.id),
                    "openid": openid,
                    "is_new_user": is_new_user
                }
            )
            
            return result
            
        except WechatError as e:
            logger.error(f"微信小程序登录失败: {str(e)}", 
                         extra={"request_id": trace_key, "code": code[:4]})
            raise
        except Exception as e:
            logger.error(f"微信小程序登录过程中出现未知错误: {str(e)}", 
                         exc_info=True, 
                         extra={"request_id": trace_key})
            raise WechatError(f"登录失败: {str(e)}") from e
    
    @gate_keeper()
    @log_service_call(method_type="wechat", tollgate="20-3")
    async def verify_token(self, token: str, db: AsyncSession) -> Dict[str, Any]:
        """
        验证JWT token并返回用户信息
        
        Args:
            token: JWT token
            db: 数据库会话
            
        Returns:
            Dict: 包含用户ID和openid
            
        Raises:
            WechatError: token验证错误
        """
        trace_key = request_ctx.get_trace_key()
        
        try:
            # 1. 解析并验证token
            payload = jwt.decode(
                token, 
                self.token_secret, 
                algorithms=[self.token_algorithm]
            )
            
            # 2. 获取用户ID和openid
            user_id = payload.get("sub")
            openid = payload.get("openid")
            
            if not user_id or not openid:
                raise WechatError("Token格式无效")
            
            # 3. 查询用户是否存在
            user = await self._get_user_by_id(db, user_id)
            if not user:
                raise WechatError("用户不存在")
            
            # 4. 验证openid是否匹配
            if user.open_id != openid:
                logger.warning(
                    f"Token中的openid与用户记录不匹配: {openid} vs {user.open_id}",
                    extra={"request_id": trace_key, "user_id": user_id}
                )
                raise WechatError("Token信息不匹配")
            
            # 5. 更新用户最后活跃时间
            user.last_active_time = datetime.now()
            await db.commit()
            
            return {
                "user_id": str(user.id),
                "openid": openid,
                "exp": payload.get("exp")
            }
            
        except jwt.ExpiredSignatureError:
            logger.warning(f"Token已过期", extra={"request_id": trace_key})
            raise WechatError("Token已过期")
        except jwt.InvalidTokenError as e:
            logger.warning(f"无效的Token: {str(e)}", extra={"request_id": trace_key})
            raise WechatError(f"无效的Token: {str(e)}")
        except Exception as e:
            logger.error(f"验证Token时发生错误: {str(e)}", 
                         exc_info=True, 
                         extra={"request_id": trace_key})
            raise WechatError(f"Token验证失败: {str(e)}") from e
    
    @gate_keeper()
    @log_service_call(method_type="wechat", tollgate="20-4")
    async def refresh_token(self, token: str, db: AsyncSession) -> Dict[str, Any]:
        """
        刷新JWT token
        
        Args:
            token: 原JWT token
            db: 数据库会话
            
        Returns:
            Dict: 包含新token
            
        Raises:
            WechatError: token刷新错误
        """
        trace_key = request_ctx.get_trace_key()
        
        try:
            # 先验证原token (即使过期也尝试解析)
            try:
                payload = jwt.decode(
                    token, 
                    self.token_secret, 
                    algorithms=[self.token_algorithm],
                    options={"verify_exp": False}
                )
            except jwt.InvalidTokenError as e:
                logger.warning(f"无效的Token无法刷新: {str(e)}", 
                               extra={"request_id": trace_key})
                raise WechatError(f"无法刷新无效的Token: {str(e)}")
            
            # 获取用户ID和openid
            user_id = payload.get("sub")
            openid = payload.get("openid")
            
            if not user_id or not openid:
                raise WechatError("Token格式无效")
            
            # 查询用户是否存在
            user = await self._get_user_by_id(db, user_id)
            if not user:
                raise WechatError("用户不存在")
            
            # 验证openid是否匹配
            if user.open_id != openid:
                logger.warning(
                    f"Token中的openid与用户记录不匹配: {openid} vs {user.open_id}",
                    extra={"request_id": trace_key, "user_id": user_id}
                )
                raise WechatError("Token信息不匹配")
            
            # 生成新token
            new_token = self._generate_token(user.id, openid)
            
            # 更新用户最后活跃时间
            user.last_active_time = datetime.now()
            await db.commit()
            
            logger.info(f"用户Token刷新成功: {user_id}", 
                        extra={"request_id": trace_key, "user_id": user_id})
            
            return {
                "token": new_token,
                "expires_in": self.token_expires * 86400  # 秒为单位
            }
            
        except WechatError:
            # 重新抛出已有错误
            raise
        except Exception as e:
            logger.error(f"刷新Token时发生错误: {str(e)}", 
                         exc_info=True, 
                         extra={"request_id": trace_key})
            raise WechatError(f"Token刷新失败: {str(e)}") from e
    
    @gate_keeper()
    @log_service_call(method_type="wechat", tollgate="20-5")
    async def update_user_info(self, user_id: str, user_info: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
        """
        更新用户信息
        
        Args:
            user_id: 用户ID
            user_info: 微信用户信息
            db: 数据库会话
            
        Returns:
            Dict: 更新后的用户信息
            
        Raises:
            WechatError: 更新过程中的错误
        """
        trace_key = request_ctx.get_trace_key()
        
        try:
            # 1. 查询用户是否存在
            user = await self._get_user_by_id(db, user_id)
            if not user:
                raise WechatError(f"用户不存在: {user_id}")
            
            # 2. 更新用户信息
            user.nick_name = user_info.get("nickName", user.nick_name)
            user.avatar = user_info.get("avatarUrl", user.avatar)
            user.gender = int(user_info.get("gender", user.gender or 0))
            user.country = user_info.get("country", user.country)
            user.province = user_info.get("province", user.province)
            user.city = user_info.get("city", user.city)
            user.language = user_info.get("language", user.language)
            user.is_authorized = True
            user.auth_time = datetime.now()
            
            # 3. 提交更新
            await db.commit()
            await db.refresh(user)
            
            logger.info(f"用户信息更新成功: {user_id}", 
                        extra={"request_id": trace_key, "user_id": user_id})
            
            # 4. 返回更新后的用户信息
            return {
                "user_id": str(user.id),
                "openid": user.open_id,
                "nickname": user.nick_name,
                "avatar": user.avatar,
                "gender": user.gender,
                "country": user.country,
                "province": user.province,
                "city": user.city,
                "language": user.language,
                "is_authorized": user.is_authorized
            }
            
        except WechatError:
            # 重新抛出已有错误
            raise
        except Exception as e:
            logger.error(f"更新用户信息时发生错误: {str(e)}", 
                         exc_info=True, 
                         extra={"request_id": trace_key})
            raise WechatError(f"更新用户信息失败: {str(e)}") from e
    
    @cache_result(expire_seconds=300)  # 缓存5分钟
    async def _code2session(self, code: str) -> Tuple[str, str]:
        """
        通过code获取openid和session_key
        
        Args:
            code: 微信登录临时凭证
            
        Returns:
            Tuple[str, str]: (openid, session_key)
            
        Raises:
            WechatError: 调用微信API错误
        """
        trace_key = request_ctx.get_trace_key()
        
        # 构建请求URL
        url = f"https://api.weixin.qq.com/sns/jscode2session"
        params = {
            "appid": self.appid,
            "secret": self.secret,
            "js_code": code,
            "grant_type": "authorization_code"
        }
        
        try:
            # 发送请求到微信服务器
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                # 解析响应
                result = response.json()
                
                # 检查响应状态
                if "errcode" in result and result["errcode"] != 0:
                    error_code = result.get("errcode")
                    error_msg = result.get("errmsg", "未知错误")
                    logger.error(
                        f"微信code2session接口返回错误: {error_code} - {error_msg}",
                        extra={
                            "request_id": trace_key,
                            "error_code": error_code,
                            "error_msg": error_msg
                        }
                    )
                    raise WechatError(f"获取openid失败: {error_code} - {error_msg}")
                
                # 提取openid和session_key
                openid = result.get("openid")
                session_key = result.get("session_key")
                
                if not openid or not session_key:
                    logger.error(
                        f"微信code2session接口返回数据不完整: {result}",
                        extra={"request_id": trace_key}
                    )
                    raise WechatError("获取openid或session_key失败")
                
                logger.info(
                    f"成功获取openid: {openid[:4]}...",
                    extra={"request_id": trace_key}
                )
                
                return openid, session_key
                
        except httpx.HTTPError as e:
            logger.error(
                f"请求微信code2session接口失败: {str(e)}",
                exc_info=True,
                extra={"request_id": trace_key}
            )
            raise WechatError(f"请求微信服务器失败: {str(e)}") from e
    
    async def _get_or_create_user(self, db: AsyncSession, openid: str) -> Tuple[MetaUser, bool]:
        """
        根据openid查询或创建用户
        
        Args:
            db: 数据库会话
            openid: 微信openid
            
        Returns:
            Tuple[MetaUser, bool]: (用户记录, 是否为新用户)
        """
        trace_key = request_ctx.get_trace_key()
        
        # 1. 查询用户是否存在
        stmt = select(MetaUser).where(
            and_(
                MetaUser._open_id == openid,
                MetaUser.status == 1,
                MetaUser.scope == PlatformScopeEnum.WECHAT.value
            )
        )
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            logger.info(
                f"找到现有微信用户: {user.id}",
                extra={"request_id": trace_key, "user_id": str(user.id)}
            )
            return user, False
        
        # 2. 创建新用户
        new_user = MetaUser(
            scope=PlatformScopeEnum.WECHAT.value,  # 平台范围：微信
            open_id=openid,  # 会自动加密
            only_id=openid,  # 平台内唯一ID
            nick_name="微信用户",  # 默认昵称
            gender=0,  # 默认性别：未知
            avatar="",  # 默认空头像
            status=1,  # 活跃状态
            login_count=1,  # 首次登录
            last_login_at=datetime.now(),  # 登录时间
            last_active_time=datetime.now(),  # 最后活跃时间
            is_authorized=False,  # 默认未授权获取用户信息
            wx_app_id=self.appid,  # 微信小程序ID
            sort=0,  # 默认排序值
            description="微信小程序用户",  # 描述信息
            memo=f"通过code2session接口创建于{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"  # 备注信息
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        logger.info(
            f"创建新微信用户: {new_user.id}",
            extra={"request_id": trace_key, "user_id": str(new_user.id)}
        )
        
        return new_user, True
    
    async def _get_user_by_id(self, db: AsyncSession, user_id: str) -> Optional[MetaUser]:
        """
        根据用户ID查询用户
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            Optional[MetaUser]: 用户记录或None
        """
        try:
            user_uuid = uuid.UUID(user_id)
            stmt = select(MetaUser).where(
                and_(
                    MetaUser.id == user_uuid,
                    MetaUser.status == 1  # 只查询活跃用户
                )
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except (ValueError, TypeError):
            return None
    
    async def _update_user_login_info(self, db: AsyncSession, user: MetaUser, is_new_user: bool) -> None:
        """
        更新用户登录信息
        
        Args:
            db: 数据库会话
            user: 用户记录
            is_new_user: 是否为新用户
        """
        now = datetime.now()
        
        # 如果不是新用户，更新登录次数和时间
        if not is_new_user:
            user.login_count += 1
            user.last_login_at = now
        
        # 更新最后活跃时间
        user.last_active_time = now
        
        await db.commit()
    
    def _generate_token(self, user_id: uuid.UUID, openid: str) -> str:
        """
        生成JWT token
        
        Args:
            user_id: 用户ID
            openid: 微信openid
            
        Returns:
            str: JWT token
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(days=self.token_expires)
        
        payload = {
            "iat": now,
            "exp": expires_at,
            "sub": str(user_id),
            "openid": openid,
            "type": "wechat_mini"
        }
        
        token = jwt.encode(
            payload,
            self.token_secret,
            algorithm=self.token_algorithm
        )
        
        return token