"""
用户服务模块

提供用户信息的查询和管理功能。
"""
from typing import Optional, Union
import uuid

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.models.meta_user import MetaUser
from bot_api_v1.app.services.business.user_cache_service import UserCacheService


class UserService:
    """用户服务，提供用户信息的管理和查询功能"""
    
    def __init__(self):
        """初始化用户服务"""
        self.user_cache_service = UserCacheService()
    
    async def get_user_id_by_openid(
        self, 
        db: AsyncSession, 
        openid: str,
        platform_scope: str,
        trace_key: str = None,
        operation_id: str = None
    ) -> Optional[uuid.UUID]:
        """
        通过openid获取用户ID，带缓存机制
        
        Args:
            db: 数据库会话
            openid: 用户OpenID
            platform_scope: 平台范围
            trace_key: 请求追踪键
            operation_id: 操作ID
            
        Returns:
            Optional[uuid.UUID]: 用户ID或None
        """
        # 尝试从缓存获取
        user_id = await self.user_cache_service.get_user_id(platform_scope, openid)
        if user_id:
            logger.info(
                f"[{operation_id}] 从缓存获取用户ID成功: {openid[:5]}***",
                extra={"request_id": trace_key, "user_id": str(user_id)}
            )
            return user_id
        
        # 缓存未命中，从数据库查询
        try:
            stmt_user = select(MetaUser.id).where(
                and_(
                    MetaUser._open_id == openid,
                    MetaUser.status == 1,
                    MetaUser.scope == platform_scope
                )
            ).limit(1)
            
            # 设置语句超时
            stmt_user = stmt_user.execution_options(timeout=5000)
            
            # 执行查询
            result_user = await db.execute(stmt_user)
            user_id = result_user.scalar_one_or_none()
            
            # 如果找到用户ID，存入缓存
            if user_id:
                await self.user_cache_service.set_user_id(
                    platform_scope, 
                    openid, 
                    user_id, 
                    expire_seconds=300  # 缓存1小时
                )
                logger.info(
                    f"[{operation_id}] 用户ID已缓存: {openid[:5]}***",
                    extra={"request_id": trace_key, "user_id": str(user_id)}
                )
                
            return user_id
            
        except Exception as e:
            logger.error(
                f"[{operation_id}] 查询用户ID失败: {str(e)}",
                exc_info=True,
                extra={"request_id": trace_key, "openid": openid}
            )
            return None