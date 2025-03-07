"""
签名验证模块

为API提供签名验证功能，支持多种验签算法，适配不同外部服务商。
"""
import hmac
import hashlib
import base64
import json
import time
from typing import Dict, Any, Optional, Type, Callable
import functools
from datetime import datetime, timedelta

from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.core.context import request_ctx
from bot_api_v1.app.db.session import get_db


class SignatureVerifier:
    """签名验证基类"""
    
    # 验签器注册表
    _verifiers: Dict[str, Type['SignatureVerifier']] = {}
    
    @classmethod
    def register(cls, name: str):
        """注册验签器装饰器"""
        def decorator(verifier_cls):
            cls._verifiers[name] = verifier_cls
            return verifier_cls
        return decorator
    
    @classmethod
    async def get_verifier(cls, app_id: str, sign_type: str = None, db: AsyncSession = None) -> 'SignatureVerifier':
        """
        根据app_id和签名类型获取对应的验签器
        
        Args:
            app_id: 应用ID
            sign_type: 签名类型，为None时使用应用默认配置
            db: 数据库会话
        
        Returns:
            对应的验签器实例
        
        Raises:
            ValueError: 如果找不到应用或验签器
        """
        from bot_api_v1.app.models.meta_app import MetaApp
        
        if not db:
            raise ValueError("需要数据库会话来获取应用信息")
        
        # 从数据库获取应用信息
        app = await db.get(MetaApp, app_id)
        if not app:
            raise ValueError(f"应用不存在: {app_id}")
        
        # 获取应用配置
        app_info = {
            "id": str(app.id),
            "name": app.name,
            "sign_type": app.sign_type,
            "sign_config": app.sign_config,
            "public_key": app.public_key,
            "private_key": app.private_key,
            "key_version": app.key_version,
            "domain": app.domain
        }
        
        # 检查应用状态
        if app.status != 1:
            raise ValueError(f"应用状态异常: {app.status}")
        
        # 如果未指定签名类型，尝试从应用配置获取
        app_sign_type = sign_type
        if not app_sign_type and app.sign_type:
            app_sign_type = app.sign_type

        if not app_sign_type:
            # 从app配置中获取默认签名类型
            # 假设配置存储在一个JSON字段中
            try:
                if hasattr(app, 'sign_config') and app.sign_config:
                    config = json.loads(app.sign_config)
                    app_sign_type = config.get('default_sign_type', 'hmac_sha256')
                else:
                    app_sign_type = 'hmac_sha256'  # 默认使用HMAC-SHA256
            except:
                app_sign_type = 'hmac_sha256'  # 解析失败时使用默认值
        
        # 获取验签器类
        verifier_cls = cls._verifiers.get(app_sign_type)
        if not verifier_cls:
            # 如果找不到指定的验签器，使用默认验签器
            verifier_cls = cls._verifiers.get('hmac_sha256', DefaultVerifier)
        
        # 创建验签器实例
        return verifier_cls(app_info)
    
    def __init__(self, app_info: Dict[str, Any]):
        """
        初始化验签器
        
        Args:
            app_info: 应用信息，包含密钥等
        """
        self.app_info = app_info
    
    async def verify(self, request: Request) -> bool:
        """
        验证请求签名
        
        Args:
            request: FastAPI请求对象
        
        Returns:
            验证是否通过
        """
        raise NotImplementedError("子类必须实现verify方法")


class DefaultVerifier(SignatureVerifier):
    """默认验签器，用于未指定验签类型时"""
    
    async def verify(self, request: Request) -> bool:
        """默认验签逻辑，简单检查app_id匹配"""
        app_id = request.headers.get("X-App-ID")
        return app_id == self.app_info['id']


@SignatureVerifier.register('hmac_sha256')
class HmacSha256Verifier(SignatureVerifier):
    """HMAC-SHA256验签器"""
    
    async def verify(self, request: Request) -> bool:
        """
        使用HMAC-SHA256算法验证签名
        
        步骤:
        1. 获取请求中的签名和时间戳
        2. 验证时间戳有效性
        3. 构造待签名字符串（参数按字母排序）
        4. 使用应用私钥生成签名
        5. 比较生成的签名与请求提供的签名
        
        Args:
            request: FastAPI请求对象
        
        Returns:
            验证是否通过
        """
        # 获取请求头中的签名和时间戳
        signature = request.headers.get("X-Signature")
        timestamp = request.headers.get("X-Timestamp")
        
        if not signature:
            raise ValueError("缺少签名")
        
        # 验证时间戳（可选）
        if timestamp:
            try:
                ts = int(timestamp)
                current_ts = int(time.time())
                # 时间戳不能超过5分钟
                if abs(current_ts - ts) > 300:
                    return False
            except:
                return False
        
        # 获取密钥
        private_key = self.app_info.get('private_key')
        if not private_key:
            raise ValueError("应用缺少私钥")
        
        # 读取请求体
        body = await request.body()
        body_text = body.decode('utf-8')
        
        # 构造待签名字符串
        string_to_sign = f"{body_text}"
        if timestamp:
            string_to_sign = f"{string_to_sign}&timestamp={timestamp}"
        
        # 计算签名
        hmac_obj = hmac.new(
            private_key.encode(), 
            string_to_sign.encode(), 
            hashlib.sha256
        )
        expected_signature = base64.b64encode(hmac_obj.digest()).decode()
        
        # 比较签名
        return hmac.compare_digest(expected_signature, signature)


@SignatureVerifier.register('rsa')
class RsaVerifier(SignatureVerifier):
    """RSA签名验证器"""
    
    async def verify(self, request: Request) -> bool:
        """
        使用RSA算法验证签名
        
        Args:
            request: FastAPI请求对象
        
        Returns:
            验证是否通过
        """
        # RSA验证实现...
        # 此处为简化示例，实际实现需要使用如cryptography库来处理RSA验证
        return True


def require_signature(sign_type: str = None, exempt: bool = False):
    """
    验签装饰器，用于API路由函数
    
    Args:
        sign_type: 指定验签类型，为None时使用应用默认配置
        exempt: 是否豁免验签，设为True时跳过验签
    
    Returns:
        装饰器函数
    
    用法:
        @router.post("/api/endpoint")
        @require_signature(sign_type="hmac_sha256")
        async def endpoint(request: Request):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 如果豁免验签，直接执行原函数
            if exempt:
                return await func(*args, **kwargs)
            
            # 获取请求对象
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                for key, value in kwargs.items():
                    if isinstance(value, Request):
                        request = value
                        break
            
            if not request:
                raise HTTPException(status_code=400, detail="无法获取请求对象")
            
            # 获取trace_key用于日志
            trace_key = request_ctx.get_trace_key()
            
            # 获取app_id
            app_id = request.headers.get("X-App-ID")
            if not app_id:
                logger.warning("验签失败: 缺少App ID", extra={"request_id": trace_key})
                raise HTTPException(status_code=401, detail="缺少App ID")
            
            try:
                # 获取数据库会话
                db = kwargs.get('db')
                if not db:
                    # 如果没有通过依赖注入获取db，尝试创建一个
                    db_func = get_db()
                    db = await db_func.__anext__()
                
                # 获取验签器
                verifier = await SignatureVerifier.get_verifier(app_id, sign_type, db)
                
                # 执行验签
                if not await verifier.verify(request):
                    logger.warning(f"验签失败: {app_id}", extra={"request_id": trace_key})
                    raise HTTPException(status_code=401, detail="签名验证失败")
                
                # 验签通过，记录日志
                logger.info(f"验签通过: {app_id}", extra={"request_id": trace_key})
                
                # 将app_id存入请求状态，供后续处理使用
                request.state.app_id = app_id
                
                # 执行原始处理函数
                return await func(*args, **kwargs)
                
            except ValueError as e:
                logger.error(f"验签错误: {str(e)}", extra={"request_id": trace_key})
                raise HTTPException(status_code=401, detail=str(e))
                
            except Exception as e:
                logger.error(f"验签过程发生异常: {str(e)}", extra={"request_id": trace_key})
                raise HTTPException(status_code=500, detail="验签过程发生内部错误")
            
        return wrapper
    return decorator