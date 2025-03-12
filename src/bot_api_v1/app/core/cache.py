import functools
import hashlib
import json
import time
from typing import Dict, Any, Tuple
from datetime import datetime, timedelta

# 简单的内存缓存实现
class SimpleCache:
    def __init__(self, max_size=100):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        
    def get(self, key: str) -> Any:
        """获取缓存项，如果过期或不存在则返回None"""
        if key not in self.cache:
            return None
            
        item = self.cache[key]
        # 检查是否过期
        if item['expires_at'] and datetime.now() > item['expires_at']:
            self.delete(key)
            return None
            
        return item['value']
        
    def set(self, key: str, value: Any, expire_seconds: int = None) -> None:
        """设置缓存项，可选过期时间"""
        # 如果缓存已满，移除最早的项
        if len(self.cache) >= self.max_size and key not in self.cache:
            oldest_key = min(self.cache.items(), key=lambda x: x[1]['created_at'])[0]
            self.delete(oldest_key)
            
        expires_at = None
        if expire_seconds:
            expires_at = datetime.now() + timedelta(seconds=expire_seconds)
            
        self.cache[key] = {
            'value': value,
            'created_at': datetime.now(),
            'expires_at': expires_at
        }
        
    def delete(self, key: str) -> None:
        """删除缓存项"""
        if key in self.cache:
            del self.cache[key]
            
    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()

# 创建缓存实例
script_cache = SimpleCache(max_size=500)  # 最多缓存500项

# 缓存装饰器
def cache_result(expire_seconds=86400, prefix="script_cache", skip_args=None):
    """
    缓存函数结果的装饰器
    
    Args:
        expire_seconds: 缓存过期时间(秒)，默认1天
        prefix: 缓存键前缀
        skip_args: 计算缓存键时要跳过的参数名列表
    """
    skip_args = skip_args or []
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取请求上下文和日志信息
            from bot_api_v1.app.core.context import request_ctx
            from bot_api_v1.app.core.logger import logger
            
            trace_key = request_ctx.get_trace_key()
            method_name = func.__qualname__
            
            # 检查是否强制刷新缓存
            force_refresh = kwargs.pop('force_refresh', False)
            
            # 提取URL参数(第一个非self参数通常是URL)
            url = args[1] if len(args) > 1 else kwargs.get('url')
            if not url:
                logger.warning(
                    f"缓存键生成失败：未找到URL参数",
                    extra={"request_id": trace_key}
                )
                return await func(*args, **kwargs)
            
            # 生成缓存键
            cache_key_parts = [method_name, url]
            
            # 添加其他参数作为缓存键的一部分
            filtered_kwargs = {
                k: v for k, v in kwargs.items() 
                if k not in skip_args and k != 'url' and k != 'force_refresh'
            }
            if filtered_kwargs:
                kwargs_str = json.dumps(
                    filtered_kwargs, 
                    sort_keys=True, 
                    default=str
                )
                cache_key_parts.append(kwargs_str)
            
            # 生成最终缓存键
            cache_key_str = ":".join(str(part) for part in cache_key_parts)
            cache_key = hashlib.md5(cache_key_str.encode()).hexdigest()
            full_cache_key = f"{prefix}:{cache_key}"
            
            # 不进行缓存刷新时，尝试从缓存获取结果
            if not force_refresh:
                cached_data = script_cache.get(full_cache_key)
                if cached_data:
                    logger.info(
                        f"缓存命中: {method_name}",
                        extra={"request_id": trace_key, "cache_key": full_cache_key}
                    )
                    return cached_data['result']
            
            # 缓存未命中或强制刷新，执行原函数
            logger.info(
                f"缓存{full_cache_key}未命中，执行方法: {method_name}",
                extra={"request_id": trace_key}
            )
            
            start_time = time.time()
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # 将结果存入缓存
            try:
                cache_data = {
                    "result": result,
                    "cached_at": time.time(),
                    "execution_time": execution_time,
                    "url": url
                }
                script_cache.set(
                    full_cache_key,
                    cache_data,
                    expire_seconds
                )
                logger.info(
                    f"结果已缓存: {method_name}, 耗时: {execution_time:.2f}s",
                    extra={"request_id": trace_key, "cache_key": full_cache_key}
                )
            except Exception as e:
                logger.error(
                    f"缓存结果失败: {str(e)}",
                    extra={"request_id": trace_key}
                )
            
            return result
        
        return wrapper
    
    return decorator