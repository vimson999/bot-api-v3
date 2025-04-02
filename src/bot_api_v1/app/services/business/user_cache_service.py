from typing import Optional, Any
import uuid

from bot_api_v1.app.core.cache import user_cache
from bot_api_v1.app.core.logger import logger


class UserCacheService:
    """用户相关信息缓存服务"""
    
    @staticmethod
    async def get_user_id(platform: str, openid: str) -> Optional[uuid.UUID]:
        """
        从缓存获取用户ID
        
        Args:
            platform: 平台标识
            openid: 用户的OpenID
            
        Returns:
            Optional[uuid.UUID]: 用户ID或None
        """
        cache_key = f"user_id:{platform}:{openid}"
        user_id_str = user_cache.get(cache_key)
        
        if user_id_str:
            try:
                return uuid.UUID(user_id_str)
            except (ValueError, TypeError):
                logger.warning(f"缓存中的用户ID格式无效: {user_id_str}")
                return None
        
        return None
    
    @staticmethod
    async def set_user_id(platform: str, openid: str, user_id: uuid.UUID, expire_seconds: int = 3600) -> None:
        """
        缓存用户ID
        
        Args:
            platform: 平台标识
            openid: 用户的OpenID
            user_id: 用户ID
            expire_seconds: 过期时间(秒)，默认1小时
        """
        cache_key = f"user_id:{platform}:{openid}"
        user_cache.set(cache_key, str(user_id), expire_seconds)
        logger.debug(f"用户ID已缓存: {platform}:{openid} -> {user_id}")
    
    @staticmethod
    async def delete_user_id(platform: str, openid: str) -> None:
        """
        删除缓存的用户ID
        
        Args:
            platform: 平台标识
            openid: 用户的OpenID
        """
        cache_key = f"user_id:{platform}:{openid}"
        user_cache.delete(cache_key)
        logger.debug(f"用户ID缓存已删除: {platform}:{openid}")
    
    # 可以添加更多用户相关的缓存方法