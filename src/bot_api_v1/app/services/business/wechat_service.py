"""
微信小程序服务模块

提供微信小程序登录、用户信息解密等功能。
"""
# 在文件开头整理导入语句
from itertools import product
import json
import time
import uuid
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

import secrets  # 添加到文件顶部

import hashlib  # 添加这一行
import aiohttp
import httpx
import jwt
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.services.business.order_service import OrderService
from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.core.cache import cache_result, script_cache
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper
from bot_api_v1.app.models.meta_user import MetaUser, PlatformScopeEnum
from bot_api_v1.app.constants.log_types import LogEventType, LogSource
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.services.business.points_service import PointsService
from bot_api_v1.app.models.meta_auth_key import MetaAuthKey
from sqlalchemy import func


class WechatError(Exception):
    """微信服务操作过程中出现的错误"""
    pass


class WechatService:
    """微信小程序服务，提供微信登录、用户信息等功能"""
    
    def __init__(self):
        """初始化微信服务"""
        self.appid = settings.WECHAT_MINI_APPID
        self.secret = settings.WECHAT_MINI_SECRET

        self.mp_id = settings.WECHAT_MP_APPID
        self.mp_secret = settings.WECHAT_MP_SECRET
        self.mp_token = settings.WECHAT_MP_TOKEN  # 添加这一行
        
        self.token_secret = settings.JWT_SECRET_KEY
        self.token_algorithm = "HS256"
        self.token_expires = 7  # 7天

        self.points_service = PointsService()
        self.order_service = OrderService()  # 添加OrderService实例

    
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

    async def check_user_exists_by_openid(self, openid: str, db: AsyncSession) -> bool:
        """
        检查用户是否存在于meta_user表中
        
        Args:
            openid: 微信用户的OpenID
            db: 数据库会话
        
        Returns:
            bool: 用户是否存在
        """
        
        try:
            # 查询数据库中是否存在该openid的用户
            result = await db.execute(
                select(MetaUser).where(
                    and_(
                        MetaUser._open_id == openid,  # 使用 _open_id 而不是 open_id
                        MetaUser.scope == PlatformScopeEnum.WECHAT.value  # 确保是微信用户
                    )
                )
            )
            user = result.scalars().first()
            
            return user is not None
        except Exception as e:
            logger.error(f"检查用户是否存在时出错: {str(e)}", exc_info=True)
            raise WechatError(f"检查用户是否存在时出错: {str(e)}")
    
    async def update_mp_user_info(self, openid: str, db: AsyncSession) -> Dict[str, Any]:
        """
        更新已存在用户的信息
        
        Args:
            openid: 微信用户的OpenID
            db: 数据库会话
        
        Returns:
            Dict: 更新后的用户信息
        """        
        try:
            # 查询用户
            result = await db.execute(
                select(MetaUser).where(MetaUser._open_id == openid)
                .where(MetaUser.scope == PlatformScopeEnum.WECHAT.value)
                .where(MetaUser.status == 1)
            )
            user = result.scalars().first()
            
            if not user:
                raise WechatError(f"用户不存在: {openid}")
            
            # 从微信API获取用户信息
            wx_user_info = await self._get_mp_user_info_from_wechat(openid)
            
            # 更新用户信息
            user.nick_name = wx_user_info.get("nickname", user.nick_name)
            user.avatar = wx_user_info.get("headimgurl", user.avatar)
            user.gender = wx_user_info.get("sex", user.gender)
            user.country = wx_user_info.get("country", user.country)
            user.province = wx_user_info.get("province", user.province)
            user.city = wx_user_info.get("city", user.city)
            user.updated_at = datetime.now()
# 处理用户状态
            if user.status != 1:
                user.status = 1
                user.memo = f"{user.memo or ''}; 用户于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 重新订阅"
                logger.info(
                    f"用户 {openid} 重新订阅，状态已更新为活跃",
                    extra={"request_id": request_ctx.get_trace_key(), "openid": openid}
                )

            await db.commit()
            await db.refresh(user)
            
            # 返回用户信息
            return {
                "user_id": str(user.id),
                "openid": user.open_id,
                "nickname": user.nick_name,
                "avatar": user.avatar,
                "gender": user.gender,
                "country": user.country,
                "province": user.province,
            }
        except Exception as e:
            logger.error(f"更新用户信息时出错: {str(e)}", exc_info=True)
            raise WechatError(f"更新用户信息时出错: {str(e)}")
    
    
    
    async def create_mp_user(self, openid: str, db: AsyncSession) -> Dict[str, Any]:
        """
        创建新用户
        
        Args:
            openid: 微信用户的OpenID
            db: 数据库会话
        
        Returns:
            Dict: 新创建的用户信息
        """        
        try:
            # 从微信API获取用户信息
            wx_user_info = await self._get_mp_user_info_from_wechat(openid)
            
            # 创建新用户
            new_user = MetaUser(
                scope=PlatformScopeEnum.WECHAT.value,  # 平台范围：微信公众号
                open_id=openid,  # 微信openid
                only_id=openid,  # 平台内唯一ID
                nick_name=wx_user_info.get("nickname", "微信用户"),
                avatar=wx_user_info.get("headimgurl", ""),
                gender=int(wx_user_info.get("sex", 0)),
                country=wx_user_info.get("country", ""),
                province=wx_user_info.get("province", ""),
                city=wx_user_info.get("city", ""),
                status=1,  # 活跃状态
                login_count=1,  # 首次登录
                last_login_at=datetime.now(),  # 登录时间
                last_active_time=datetime.now(),  # 最后活跃时间
                is_authorized=True,  # 已授权获取用户信息
                wx_app_id=settings.WECHAT_MP_APPID,  # 微信公众号APPID
                sort=0,  # 默认排序值
                description="微信公众号用户",  # 描述信息
                memo=f"通过公众号关注创建于{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",  # 备注信息
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            
            # 返回用户信息
            return {
                "user_id": str(new_user.id),
                "open_id": new_user.open_id,  # 修改为open_id
                "nickname": new_user.nick_name,
                "avatar": new_user.avatar,
                "gender": new_user.gender,
                "country": new_user.country,
                "province": new_user.province,
                "city": new_user.city
            }
        except Exception as e:
            logger.error(f"创建用户时出错: {str(e)}", exc_info=True)
            raise WechatError(f"创建用户时出错: {str(e)}")

    async def _get_mp_user_info_from_wechat(self, openid: str) -> Dict[str, Any]:
        """
        从微信公众号API获取用户信息
        
        Args:
            openid: 微信用户的OpenID
        
        Returns:
            Dict: 微信用户信息
        """
        try:
            # 获取访问令牌
            access_token = await self._get_mp_access_token()
            
            # 调用微信API获取用户信息
            url = f"https://api.weixin.qq.com/cgi-bin/user/info?access_token={access_token}&openid={openid}&lang=zh_CN"
            
            logger.info(f"Fetching user info for openid: {openid}")
            logger.info(f"Request URL: {url}") 

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"获取微信用户信息失败: HTTP状态码 {response.status}")
                        # 返回默认用户信息
                        return {
                            "nickname": "微信用户",
                            "headimgurl": "",
                            "sex": 0,
                            "country": "",
                            "province": "",
                            "city": ""
                        }
                    
                    data = await response.json()
                    
                    if "errcode" in data and data["errcode"] != 0:
                        logger.error(f"获取微信用户信息失败: {data.get('errmsg', '未知错误')}")
                        # 返回默认用户信息
                        return {
                            "nickname": "微信用户",
                            "headimgurl": "",
                            "sex": 0,
                            "country": "",
                            "province": "",
                            "city": ""
                        }
                    
                    return data
        except Exception as e:
            logger.error(f"获取微信用户信息时出错: {str(e)}", exc_info=True)
            # 返回默认用户信息
            return {
                "nickname": "微信用户",
                "headimgurl": "",
                "sex": 0,
                "country": "",
                "province": "",
                "city": ""
            }
    
    async def _get_mp_access_token(self) -> str:
        """
        获取微信公众号访问令牌，使用稳定版接口 (stable_token)
        
        包含：
        - 缓存机制和自动刷新逻辑
        - 多层次回退策略：缓存旧令牌 -> 备用令牌 -> 报错
        
        Returns:
            str: 微信公众号访问令牌
        """
        cache_key = f"wechat:mp:access_token:{settings.WECHAT_MP_APPID}"
        
        try:
            # 尝试从缓存获取令牌
            token_data = self._get_cached_token(cache_key)
            if token_data and token_data.get("expires_at", 0) > time.time() + 300:
                logger.debug("从缓存获取微信公众号访问令牌")
                return token_data.get("access_token")
            
            # 缓存不存在或即将过期，使用稳定版接口重新获取
            logger.info("使用稳定版接口获取微信公众号访问令牌")
            
            # 构建请求参数 - 使用稳定版接口
            url = "https://api.weixin.qq.com/cgi-bin/stable_token"
            payload = {
                "grant_type": "client_credential",
                "appid": settings.WECHAT_MP_APPID,
                "secret": settings.WECHAT_MP_SECRET,
                "force_refresh": False  # 可选参数，避免无必要刷新
            }
            
            # 发送POST请求到微信服务器
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                
                # 解析响应
                result = response.json()
                
                # 检查响应状态
                if "errcode" in result and result.get("errcode", 0) != 0:
                    error_code = result.get("errcode")
                    error_msg = result.get("errmsg", "未知错误")
                    logger.error(f"获取微信公众号访问令牌失败: {error_code} - {error_msg}")
                    
                    # 使用回退策略
                    return self._fallback_token_strategy(cache_key, error_msg)
                
                # 提取访问令牌和过期时间
                access_token = result.get("access_token")
                expires_in = result.get("expires_in", 7200)  # 默认2小时
                
                if not access_token:
                    logger.error("微信返回的访问令牌为空")
                    return self._fallback_token_strategy(cache_key, "令牌为空")
                
                # 缓存访问令牌
                token_data = {
                    "access_token": access_token,
                    "expires_at": time.time() + expires_in
                }
                
                # 缓存时间设置为令牌有效期减去5分钟，避免使用临近过期的令牌
                script_cache.set(
                    cache_key,
                    token_data,
                    expire_seconds=expires_in - 300  # 提前5分钟过期
                )
                
                logger.info(f"成功获取微信公众号访问令牌，有效期: {expires_in}秒")
                return access_token
                
        except Exception as e:
            logger.error(f"获取微信访问令牌时出错: {str(e)}", exc_info=True)
            return self._fallback_token_strategy(cache_key, str(e))
        
    def _get_cached_token(self, cache_key):
        """从缓存中安全地获取令牌数据"""
        cached = script_cache.get(cache_key)
        if not cached:
            return None
            
        # 处理不同格式的缓存数据
        if isinstance(cached, dict):
            if "access_token" in cached:
                return cached
            elif "value" in cached and isinstance(cached["value"], dict):
                return cached["value"]
        
        return None
        
    def _fallback_token_strategy(self, cache_key, error_msg):
        """统一处理令牌获取失败的回退策略"""
        # 1. 尝试从缓存获取旧令牌
        token_data = self._get_cached_token(cache_key)
        if token_data and token_data.get("access_token"):
            logger.warning("使用缓存中的旧访问令牌")
            return token_data.get("access_token")
        
        # 2. 如果有配置的备用令牌，返回备用令牌
        if hasattr(settings, "WECHAT_MP_ACCESS_TOKEN_FALLBACK"):
            logger.warning("使用备用访问令牌")
            return settings.WECHAT_MP_ACCESS_TOKEN_FALLBACK
            
        # 3. 没有可用的回退选项，抛出异常
        raise WechatError(f"获取访问令牌失败: {error_msg}")
    
    async def verify_mp_signature(self, signature: str, timestamp: str, nonce: str) -> bool:
        """
        验证微信公众号服务器签名
        
        Args:
            signature: 微信加密签名
            timestamp: 时间戳
            nonce: 随机数
        
        Returns:
            bool: 签名是否有效
        """
        
        try:
            # 获取token
            token = settings.WECHAT_MP_TOKEN
            
            # 1. Create a list with token, timestamp, and nonce
            tmp_list = [token, timestamp, nonce]
            
            # 2. Sort the list
            tmp_list.sort()
            
            # 3. Join the sorted list into a single string
            tmp_str = ''.join(tmp_list)
            
            # 4. SHA1 hash the string
            sha1_str = hashlib.sha1(tmp_str.encode('utf-8')).hexdigest()
            
            # 5. Compare the hashed string with the signature
            return sha1_str == signature
        except Exception as e:
            logger.error(f"验证微信签名时出错: {str(e)}", exc_info=True)
            return False
    

    @gate_keeper()
    @log_service_call()
    async def handle_user_subscribe(self, openid: str, trace_key: str, db: AsyncSession) -> Dict[str, Any]:
        """
        处理用户关注事件
        
        Args:
            openid: 用户的OpenID
            trace_key: 请求追踪ID
            db: 数据库会话
        
        Returns:
            Dict: 用户信息和处理结果
        """
        try:
            # 检查用户是否存在
            user_exists = await self.check_user_exists_by_openid(openid, db)
            
            user_info = {}
            if user_exists:
                # 更新已存在用户信息
                logger.info(
                    f"更新已存在用户信息: {openid}",
                    extra={"request_id": trace_key, "openid": openid}
                )
                user_info = await self.update_mp_user_info(openid, db)
            else:
                # 创建新用户
                logger.info(
                    f"创建新用户: {openid}",
                    extra={"request_id": trace_key, "openid": openid}
                )
                user_info = await self.create_mp_user(openid, db)
            
            # 获取访问令牌并发送模板消息
            try:
                access_token = await self._get_mp_access_token()
                if access_token:
                    await self.send_welcome_template_message(access_token, openid)
            except Exception as e:
                logger.error(f"发送欢迎模板消息失败: {str(e)}", exc_info=True)
            
            logger.info_to_db(
                f"创建新用户，用户关注公众号处理成功: {openid}",
                extra={
                    "request_id": trace_key,
                    "openid": openid,
                    "is_new_user": not user_exists
                }
            )
            
            return {
                "userInfo": user_info,
                "is_new_user": not user_exists
            }
            
        except Exception as e:
            logger.error(f"处理用户关注事件失败: {str(e)}", exc_info=True)
            raise WechatError(f"处理用户关注事件失败: {str(e)}")
    
    async def send_template_message(
            self,  # 注意这里添加了self参数
            access_token: str,
            open_id: str,
            template_data: Dict[str, Any],
            template_id: Optional[str] = '0QbSRPz7YAIWxtgcNmC4SxrEEXlpOyji33zkKDQ6Xnc'
        ) -> Dict[str, Any]:
            """
            发送模板消息
            
            Args:
                access_token: 访问令牌
                open_id: 用户的OpenID
                template_data: 模板数据
                template_id: 模板ID
            
            Returns:
                Dict: 发送结果
            """
            url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}"
            
            message_data = {
                "touser": open_id,
                "template_id": template_id,
                "data": template_data
            }
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=message_data)
                    response.raise_for_status()
                    result = response.json()
                    
                    if result.get("errcode", 0) != 0:
                        logger.error(f"发送模板消息失败: {result}")
                        raise WechatError(f"发送模板消息失败: {result.get('errmsg', '未知错误')}")
                        
                    logger.info(f"成功发送模板消息给用户: {open_id}")
                    return result
                    
            except Exception as e:
                logger.error(f"发送模板消息时出错: {str(e)}", exc_info=True)
                raise WechatError(f"发送模板消息失败: {str(e)}")

    async def send_welcome_template_message(
        self, 
        access_token: str, 
        openid: str, 
        template_id: str = 'nEM5TKmzJ6IYNDpCk4Yr56bIcrIRquaHaXyKR6dleXU'
    ):
        """
        发送欢迎模板消息
        
        Args:
            access_token: 访问令牌
            openid: 用户的OpenID
            template_id: 模板ID
        """
        template_data = {
            "userName": {
                "value": "欢迎关注我们！",
                "color": "#173177"
            }
        }
        
        return await self.send_template_message(
            access_token=access_token,
            open_id=openid,
            template_data=template_data,
            template_id=template_id
        )

    @gate_keeper()
    @log_service_call()
    async def handle_menu_click_event(self, event_key: str, openid: str, db: AsyncSession) -> None:
        """
        处理菜单点击事件并发送文本消息
        
        Args:
            event_key: 菜单项的key值
            openid: 用户的OpenID
            db: 数据库会话
        """
        trace_key = request_ctx.get_trace_key()
        logger.info_to_db(
            f"处理菜单点击事件: {event_key}，用户: {openid},时间: {datetime.now()}",
            extra={"request_id": trace_key, "openid": openid, "event_key": event_key}
        )
        
        try:
            # 获取菜单回复文本
            reply_text = await self._get_menu_reply_text(event_key, openid, db)
            
            # 发送文本消息
            await self.send_text_message(openid, reply_text)
            
            logger.info(
                f"菜单点击事件处理成功: {event_key}",
                extra={"request_id": trace_key, "openid": openid, "event_key": event_key}
            )
            
        except WechatError as e:
            error_msg = f"处理菜单点击事件失败: {str(e)}"
            logger.error(error_msg, extra={"request_id": trace_key, "openid": openid})
            await self.send_text_message(openid, "很抱歉，服务暂时不可用，请稍后重试。")
            
        except Exception as e:
            error_msg = f"处理菜单点击事件时发生未知错误: {str(e)}"
            logger.error(
                error_msg,
                exc_info=True,
                extra={"request_id": trace_key, "openid": openid, "event_key": event_key}
            )
            await self.send_text_message(openid, "系统繁忙，请稍后重试。")

    @gate_keeper()
    @log_service_call()
    async def _get_menu_reply_text(self, event_key: str, openid: str, db: AsyncSession) -> str:
        """
        获取菜单回复文本
        
        Args:
            event_key: 菜单项的key值
            openid: 用户的OpenID
            db: 数据库会话
            
        Returns:
            str: 回复文本
        """
        trace_key = request_ctx.get_trace_key()
        
        try:
            if event_key == "CHECK_BALANCE":
                return await self._get_user_points_info(openid, db)
            elif event_key == "GET_BENEFITS":
                return await self._handle_get_benefits(openid, db)
            elif event_key == "RECHARGE":
                return "2025年首次点击【积分】-【领福利】免费送您100积分，试用后可通过充值获得积分。"
            elif event_key == "QUERY_API_KEY":
                api_key_info = await self._get_user_api_key_info(openid, db)
                if api_key_info:
                    expired_date = api_key_info["expired_at"].strftime("%Y-%m-%d %H:%M:%S")
                    return f"您的API KEY为：{api_key_info['key_value']}\n过期时间：{expired_date}"
                else:
                    return "未找到您的API KEY信息。" 
            elif event_key == "NEW_API_KEY":
                return await self._handle_new_api_key_request(openid, db)
            elif event_key == "RESET_API_KEY":
                return await self._reset_user_api_key(openid, db)
            elif event_key == "FEISHU_SHEET":
                return "飞书表格使用说明：请访问https://example.com/feishu-sheet"
            else:
                logger.warning(
                    f"收到未知的菜单命令: {event_key}",
                    extra={"request_id": trace_key, "openid": openid}
                )
                return "未知的菜单命令"
        except Exception as e:
            logger.error(
                f"生成菜单回复文本失败: {str(e)}",
                exc_info=True,
                extra={"request_id": trace_key, "openid": openid, "event_key": event_key}
            )
            raise WechatError(f"生成回复文本失败: {str(e)}")

    async def _get_user_points_info(self, openid: str, db: AsyncSession) -> str:
        """获取用户积分信息文本"""
        try:
            points_info = await self.points_service.get_user_points(openid, db)
            
            # 构建积分信息消息
            reply_text = (
                f"您的积分详情：\n"
                f"总积分：{points_info['available_points']}\n"
                f"可用积分：{points_info['available_points']}"
            )
            
            # # 添加即将过期积分提醒
            # if points_info['expiring_soon']:
            #     expiring = points_info['expiring_soon'][0]
            #     reply_text += f"\n\n温馨提醒：您有 {expiring['points']} 积分将于 {expiring['expire_time'][:10]} 过期"
            
            return reply_text
        except Exception as e:
            logger.error(f"查询积分失败: {str(e)}", exc_info=True)
            return "查询积分失败，请稍后重试。"

    @gate_keeper()
    @log_service_call()
    async def send_text_message(self, openid: str, text: str) -> None:
        """
        发送文本消息
        
        Args:
            openid: 用户的OpenID
            text: 要发送的文本内容
        """
        try:
            access_token = await self._get_mp_access_token()
            url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={access_token}"
            
            message_data = {
                "touser": openid,
                "msgtype": "text",
                "text": {
                    "content": text
                }
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:  # 添加超时设置
                response = await client.post(url, json=message_data)
                response.raise_for_status()
                result = response.json()
                
                # 更健壮的错误检查
                if isinstance(result, dict) and result.get("errcode", 0) != 0:
                    logger.error(f"发送文本消息失败: {result}")
                    raise WechatError(f"发送文本消息失败: {result.get('errmsg', '未知错误')}")
                    
                logger.info_to_db(f"成功发送文本消息给用户: {openid}, 内容: {text}")
                
        except (KeyError, TypeError) as e:
            # 处理结果解析错误
            logger.error(f"解析微信API响应时出错: {str(e)}", exc_info=True)
            raise WechatError(f"解析微信API响应失败: {str(e)}")
        except Exception as e:
            logger.error(f"发送文本消息时出错: {str(e)}", exc_info=True)
            raise WechatError(f"发送文本消息失败: {str(e)}")


    async def create_wechat_menu(self, access_token: str):
        """
        创建微信公众号自定义菜单
        
        Args:
            access_token: 微信访问令牌
        """
        url = f"https://api.weixin.qq.com/cgi-bin/menu/create?access_token={access_token}"
        
        from urllib.parse import quote
        
        product_list_path = f"{settings.DOMAIN_API_URL}/api/wechat_mp/product/list"
        # 确保URL正确编码 - 这是关键修复点
        encoded_uri = quote(product_list_path, safe='')      
        # 构建完整的菜单URL
        menu_url = f"https://open.weixin.qq.com/connect/oauth2/authorize?appid={self.mp_id}&redirect_uri={encoded_uri}&response_type=code&scope=snsapi_userinfo&state=shop#wechat_redirect"
        logger.info(f"menu_url: {menu_url}")
        
        # 定义菜单结构
        menu_data = {
            "button": [
                {
                    "name": "积分",
                    "sub_button": [
                        {
                            "type": "click",
                            "name": "查余额",
                            "key": "CHECK_BALANCE"
                        },
                        {
                            "type": "click",
                            "name": "领福利",
                            "key": "GET_BENEFITS"
                        }
                        # ,
                        # {
                        #     "type": "click",
                        #     "name": "爷充值",
                        #     "key": "RECHARGE"
                        # },
                        # {
                        #     "type": "view",
                        #     "name": "土豪通道",
                        #     "url": menu_url
                        # }
                    ]
                },
                {
                    "name": "API KEY",
                    "sub_button": [
                        {
                            "type": "click",
                            "name": "查询",
                            "key": "QUERY_API_KEY"
                        },
                        {
                            "type": "click",
                            "name": "新建",
                            "key": "NEW_API_KEY"
                        },
                        {
                            "type": "click",
                            "name": "重置",
                            "key": "RESET_API_KEY"
                        }
                    ]
                },
                {
                    "name": "应用场景",
                    "sub_button": [
                        {
                            "type": "click",
                            "name": "飞书表格",
                            "key": "FEISHU_SHEET"
                        }
                        # ,
                        # {
                        #     "type": "click",
                        #     "name": "爷充值",
                        #     "key": "RECHARGE"
                        # },
                        # {
                        #     "type": "view",
                        #     "name": "土豪通道",
                        #     "url": menu_url
                        # }
                    ]
                }
            ]
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=menu_data)
                response.raise_for_status()
                result = response.json()
                
                if result.get("errcode", 0) != 0:
                    logger.error(f"创建菜单失败: {result}")
                    raise WechatError(f"创建菜单失败: {result.get('errmsg', '未知错误')}")
                
                # logger.info_to_db("成功创建微信公众号菜单")
                
        except Exception as e:
            logger.error(f"创建菜单时出错: {str(e)}", exc_info=True)
            raise WechatError(f"创建菜单失败: {str(e)}")


        
    async def _get_user_api_key_info(self, openid: str, db: AsyncSession) -> Optional[Dict[str, Any]]:
        """
        根据openid查询用户的API Key信息
        
        Args:
            openid: 微信用户的OpenID
            db: 数据库会话
            
        Returns:
            Optional[Dict[str, Any]]: 用户的API Key信息或None
        """
        try:
            # 优化查询：直接联表查询，减少数据库往返
            stmt = select(
                MetaAuthKey.key_value, 
                MetaAuthKey.expired_at
            ).join(
                MetaUser, 
                and_(
                    MetaUser.id == MetaAuthKey.user_id,
                    MetaUser._open_id == openid,
                    MetaUser.status == 1,
                    MetaUser.scope == PlatformScopeEnum.WECHAT.value
                )
            ).where(
                MetaAuthKey.key_status == 1,
                MetaAuthKey.status == 1,
                MetaAuthKey.expired_at > datetime.now()
            )
            
            result = await db.execute(stmt)
            api_key_info = result.first()
            
            if api_key_info:
                return {
                    "key_value": api_key_info[0],
                    "expired_at": api_key_info[1]
                }
            return None
        except Exception as e:
            logger.error(f"查询API Key信息时出错: {str(e)}", exc_info=True)
            return None

    async def _reset_user_api_key(self, openid: str, db: AsyncSession) -> str:
        """
        重置用户的API KEY
        
        Args:
            openid: 微信用户的OpenID
            db: 数据库会话
            
        Returns:
            str: 重置结果消息
        """
        try:
            # 1. 查询用户ID
            stmt_user = select(MetaUser.id).where(MetaUser._open_id == openid).where(
                MetaUser.status == 1,
                MetaUser.scope == PlatformScopeEnum.WECHAT.value
            )
            result_user = await db.execute(stmt_user)
            user_id = result_user.scalar_one_or_none()
            
            if not user_id:
                return "未找到用户信息，无法重置API KEY"
            
            # 2. 使现有API KEY失效
            await db.execute(
                update(MetaAuthKey)
                .where(MetaAuthKey.user_id == user_id)
                .where(MetaAuthKey.key_status == 1)  # 只更新当前有效的KEY
                .values(
                    key_status=0,  # 标记为失效
                    status=0,  # 标记为失效
                    updated_at=datetime.now(),  # 更新修改时间
                    description=func.concat(
                        MetaAuthKey.description, 
                        f"\n[失效于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"
                    ),  # 追加失效时间到描述
                    memo=func.concat(
                        MetaAuthKey.memo, 
                        f"\n用户 {openid} 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 重置导致失效"
                    )  # 追加失效原因到备注
                )
            )
            
            # 3. 生成新的API KEY
            new_api_key = secrets.token_hex(32)  # 生成更安全的随机令牌
            expires_at = datetime.now() + timedelta(days=365)  # 30天后过期
            
            # 4. 创建新的API KEY记录
            new_auth_key = MetaAuthKey(
                user_id=user_id,
                key_name=f"API_KEY_{datetime.now().strftime('%Y%m%d')}",  #
                key_value=new_api_key,
                key_status=1,
                status=1,
                expired_at=expires_at,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                description="通过微信公众号重置的API KEY",  # 描述信息
                memo=f"用户 {openid} 于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 重置API KEY"  # 备注信息
            )
            db.add(new_auth_key)
            await db.commit()
            
            # 5. 发送邮件通知(这里需要实现邮件发送逻辑)
            # await self._send_api_key_email(openid, new_api_key, expires_at)
            
            return f"您的API KEY已重置为：{new_api_key}\n新KEY将在{expires_at.strftime('%Y-%m-%d')}过期"
            
        except Exception as e:
            logger.error(f"重置API KEY时出错: {str(e)}", exc_info=True)
            await db.rollback()
            return "重置API KEY失败，请稍后重试"


    async def _handle_new_api_key_request(self, openid: str, db: AsyncSession) -> str:
        """
        处理新建API KEY请求
        
        Args:
            openid: 微信用户的OpenID
            db: 数据库会话
            
        Returns:
            str: 返回给用户的消息
        """
        # 检查是否已有有效API KEY
        api_key_info = await self._get_user_api_key_info(openid, db)
        if api_key_info:
            expired_date = api_key_info["expired_at"].strftime("%Y-%m-%d %H:%M:%S")
            return f"您已有有效的API KEY：{api_key_info['key_value']}\n过期时间：{expired_date}\n无需新建"
        
        # 没有有效API KEY则创建新的
        return await self._reset_user_api_key(openid, db)


    async def _handle_get_benefits(self, openid: str, db: AsyncSession) -> str:
        """
        处理用户领取福利的请求
        
        Args:
            openid: 微信用户的OpenID
            db: 数据库会话
            
        Returns:
            str: 处理结果消息
        """
        try:
            # 调用积分服务的方法，但需要处理返回结果
            result = await self.points_service.claim_first_time_points(openid, db)
            
            # 检查返回结果的格式，确保它是字符串
            if isinstance(result, dict):
                if result.get("success", False):
                    # 成功领取积分
                    points = result.get("data", {}).get("points", 100)
                    return f"恭喜您成功领取 {points} 积分！\n当前可用积分：{result.get('data', {}).get('available_points', points)}"
                else:
                    # 领取失败，返回错误消息
                    return result.get("message", "领取福利失败，请稍后重试")
            elif isinstance(result, str):
                # 如果已经是字符串，直接返回
                return result
            else:
                # 未知返回类型，返回通用消息
                return "领取福利操作已处理，请查询积分余额确认结果"
                
        except Exception as e:
            logger.error(f"处理领取福利请求时出错: {str(e)}", exc_info=True)
            return "领取福利失败，请稍后重试"



    @gate_keeper()
    @log_service_call()
    async def get_mp_user_info_from_code_h5(self, code: str) -> Dict[str, Any]:
        """
        通过code获取微信公众号用户信息(H5网页授权)
        """
        try:
            # 获取access_token
            token_url = f"https://api.weixin.qq.com/sns/oauth2/access_token?appid={self.mp_id}&secret={self.mp_secret}&code={code}&grant_type=authorization_code"
            async with httpx.AsyncClient() as client:
                response = await client.get(token_url)
                result = response.json()
            
            if "errcode" in result:
                raise WechatError(f"获取access_token失败: {result.get('errmsg', '未知错误')}")
            
            # 获取用户信息
            user_url = f"https://api.weixin.qq.com/sns/userinfo?access_token={result['access_token']}&openid={result['openid']}&lang=zh_CN"
            async with httpx.AsyncClient() as client:
                response = await client.get(user_url)
                user_info = response.json()
            
            if "errcode" in user_info:
                raise WechatError(f"获取用户信息失败: {user_info.get('errmsg', '未知错误')}")
            
            return user_info
            
        except Exception as e:
            logger.error(f"获取微信公众号用户信息失败: {str(e)}")
            raise WechatError("获取用户信息失败")

    @gate_keeper()
    @log_service_call()
    async def generate_h5_token(self, user_id :str ,openid: str) -> str:
        """
        生成H5网页授权token
        """
        payload = {
            # "sub": str(uuid.uuid4()),  # 随机用户ID
            "sub": user_id,
            "openid": openid,
            "exp": datetime.utcnow() + timedelta(hours=2)  # 2小时有效期
        }
        return jwt.encode(payload, self.token_secret, algorithm=self.token_algorithm)

    @gate_keeper()
    @log_service_call()
    async def verify_h5_token(self, token: str) -> Optional[str]:
        """
        验证H5网页授权token并返回openid
        """
        try:
            payload = jwt.decode(token, self.token_secret, algorithms=[self.token_algorithm])
            return payload.get("openid")
        except jwt.ExpiredSignatureError:
            raise WechatError("Token已过期")
        except jwt.InvalidTokenError:
            raise WechatError("无效的Token")
        except Exception as e:
            logger.error(f"验证Token失败: {str(e)}")
            raise WechatError("验证Token失败")



    # ... 现有代码 ...

    @gate_keeper()
    @log_service_call(method_type="wechat", tollgate="20-5")
    async def create_payment_order(
        self, 
        user_id: str, 
        openid: str, 
        product_id: str, 
        product_name: str,
        amount: float, 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        创建支付订单
        
        Args:
            user_id: 用户ID
            openid: 用户OpenID
            product_id: 商品ID
            product_name: 商品名称
            amount: 支付金额
            db: 数据库会话
            
        Returns:
            Dict: 包含订单信息的字典
        """
        trace_key = request_ctx.get_trace_key()
        logger.info(f"创建支付订单: user_id={user_id}, product_id={product_id}", 
                    extra={"request_id": trace_key})
        
        try:
            # 生成订单号
            order_no = f"WX{int(time.time())}{secrets.randbelow(10000):04d}"
            
            # 创建订单记录
            new_order = MetaOrder(
                order_no=order_no,
                order_type="PACKAGE",  # 或根据商品类型设置
                user_id=uuid.UUID(user_id),
                product_id=uuid.UUID(product_id),
                original_amount=amount,
                discount_amount=0,  # 可根据促销活动设置
                total_amount=amount,
                total_points=0,  # 根据商品设置
                currency="CNY",
                order_status=0,  # 待支付
                payment_channel="WECHAT",
                user_name=None,  # 可从用户信息获取
                product_snapshot={
                    "name": product_name,
                    "price": amount,
                    "id": product_id
                },
                client_ip=request_ctx.get_context().get("ip_address"),
                remark=f"微信公众号购买 {product_name}"
            )
            
            db.add(new_order)
            await db.commit()
            await db.refresh(new_order)
            
            return {
                "order_id": str(new_order.id),
                "order_no": order_no,
                "amount": amount,
                "product_name": product_name
            }
            
        except Exception as e:
            await db.rollback()
            logger.error(f"创建支付订单失败: {str(e)}", 
                        exc_info=True, 
                        extra={"request_id": trace_key})
            raise WechatError(f"创建订单失败: {str(e)}")

    @gate_keeper()
    @log_service_call(method_type="wechat", tollgate="20-6")
    async def create_jsapi_payment(
        self, 
        order_id: str, 
        openid: str, 
        product_name: str,
        total_fee: float,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        创建JSAPI支付参数
        
        Args:
            order_id: 订单ID
            openid: 用户OpenID
            product_name: 商品名称
            total_fee: 支付金额（元）
            db: 数据库会话
            
        Returns:
            Dict: 包含JSAPI支付参数的字典
        """
        trace_key = request_ctx.get_trace_key()
        logger.info(f"创建JSAPI支付参数: order_id={order_id}", 
                    extra={"request_id": trace_key})
        
        try:
            # 使用OrderService获取订单信息
            order_info = await self.order_service.get_order_info(order_id, db)
            if not order_info:
                raise WechatError("订单不存在")
            
            if order_info.order_status != 0:
                raise WechatError("订单状态不正确，无法支付")
            
            # 获取访问令牌
            access_token = await self._get_mp_access_token()
            
            # 构建微信支付统一下单参数
            nonce_str = secrets.token_hex(16)
            timestamp = str(int(time.time()))
            
            # 将元转换为分（微信支付金额单位是分）
            fee_in_cents = int(total_fee * 100)
            
            # 构建统一下单请求参数
            unifiedorder_data = {
                "appid": self.mp_id,
                "mch_id": settings.WECHAT_MERCHANT_ID,  # 商户号
                "nonce_str": nonce_str,
                "body": f"{product_name}",  # 商品描述
                "out_trade_no": order_info.order_no,  # 商户订单号
                "total_fee": fee_in_cents,  # 订单金额（分）
                "spbill_create_ip": request_ctx.get_context().get("ip_address", "127.0.0.1"),  # 终端IP
                "notify_url": f"{settings.DOMAIN_API_URL}/api/wechat_mp/payment/notify",  # 支付结果通知地址
                "trade_type": "JSAPI",  # 交易类型
                "openid": openid  # 用户标识
            }
            
            # 生成签名
            sign_str = "&".join([f"{k}={unifiedorder_data[k]}" for k in sorted(unifiedorder_data.keys())])
            sign_str += f"&key={settings.WECHAT_MERCHANT_KEY}"  # 商户密钥
            unifiedorder_data["sign"] = hashlib.md5(sign_str.encode()).hexdigest().upper()
            
            # 将字典转为XML
            xml_data = "<xml>"
            for k, v in unifiedorder_data.items():
                xml_data += f"<{k}>{v}</{k}>"
            xml_data += "</xml>"
            
            # 调用微信支付统一下单接口
            url = "https://api.mch.weixin.qq.com/pay/unifiedorder"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, content=xml_data, headers={"Content-Type": "application/xml"})
                response.raise_for_status()
                
                # 解析XML响应
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)
                result = {child.tag: child.text for child in root}
                
                # 检查返回结果
                if result.get("return_code") != "SUCCESS" or result.get("result_code") != "SUCCESS":
                    error_msg = result.get("return_msg") or result.get("err_code_des", "未知错误")
                    logger.error(f"微信支付统一下单失败: {error_msg}", 
                                extra={"request_id": trace_key, "order_id": order_id})
                    raise WechatError(f"微信支付下单失败: {error_msg}")
                
                # 获取预支付交易会话标识
                prepay_id = result.get("prepay_id")
                if not prepay_id:
                    raise WechatError("获取prepay_id失败")
                
                # 构建JSAPI支付参数
                pay_params = {
                    "appId": self.mp_id,
                    "timeStamp": timestamp,
                    "nonceStr": nonce_str,
                    "package": f"prepay_id={prepay_id}",
                    "signType": "MD5"
                }
                
                # 生成支付签名
                pay_sign_str = "&".join([f"{k}={pay_params[k]}" for k in sorted(pay_params.keys())])
                pay_sign_str += f"&key={settings.WECHAT_MERCHANT_KEY}"
                pay_params["paySign"] = hashlib.md5(pay_sign_str.encode()).hexdigest().upper()
                
                # 更新订单状态为支付处理中
                await self.order_service.update_order_status(order_id, 1, db=db)
                
                # 记录支付信息到日志
                logger.info_to_db(
                    f"成功创建JSAPI支付参数: order_id={order_id}, prepay_id={prepay_id}",
                    extra={"request_id": trace_key, "order_id": order_id, "openid": openid}
                )
                
                # 添加额外信息方便前端使用
                pay_params["order_id"] = order_id
                pay_params["total_fee"] = total_fee
                pay_params["product_name"] = product_name
                
                return pay_params
            
        except WechatError:
            # 重新抛出已有错误
            raise
        except Exception as e:
            logger.error(f"创建JSAPI支付参数失败: {str(e)}", 
                        exc_info=True, 
                        extra={"request_id": trace_key})
            raise WechatError(f"创建支付参数失败: {str(e)}")

