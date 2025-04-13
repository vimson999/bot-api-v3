# bot_api_v1/app/core/cache.py (已添加调试日志)

import functools
import hashlib
import json
import time
from typing import Dict, Any, Tuple
from datetime import datetime, timedelta
import logging # <-- 添加了顶层导入

import redis # 导入同步 redis 库
import urllib.parse 
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger # 导入 logger 实例

# 简单的内存缓存实现 (保持不变)
class SimpleCache:
    def __init__(self, max_size=100):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size
        
    def get(self, key: str) -> Any:
        if key not in self.cache: return None
        item = self.cache[key]
        if item['expires_at'] and datetime.now() > item['expires_at']:
            self.delete(key)
            return None
        return item['value']
        
    def set(self, key: str, value: Any, expire_seconds: int = None) -> None:
        if len(self.cache) >= self.max_size and key not in self.cache:
            oldest_key = min(self.cache.items(), key=lambda x: x[1]['created_at'])[0]
            self.delete(oldest_key)
        expires_at = None
        if expire_seconds:
            expires_at = datetime.now() + timedelta(seconds=expire_seconds)
        self.cache[key] = {'value': value, 'created_at': datetime.now(), 'expires_at': expires_at}
        
    def delete(self, key: str) -> None:
        if key in self.cache: del self.cache[key]
            
    def clear(self) -> None:
        self.cache.clear()

# 创建缓存实例 (保持不变)
script_cache = SimpleCache(max_size=500)
user_cache = SimpleCache(max_size=1000)

# 异步缓存装饰器 (保持不变)
def cache_result(expire_seconds=86400, prefix="script_cache", skip_args=None):
    skip_args = skip_args or []
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            from bot_api_v1.app.core.context import request_ctx
            # logger 已经在顶部导入
            trace_key = request_ctx.get_trace_key()
            method_name = func.__qualname__
            force_refresh = kwargs.pop('force_refresh', False)
            url = args[1] if len(args) > 1 else kwargs.get('url')
            if not url:
                logger.warning(f"缓存键生成失败：未找到URL参数", extra={"request_id": trace_key})
                return await func(*args, **kwargs)
            cache_key_parts = [method_name, url]
            filtered_kwargs = { k: v for k, v in kwargs.items() if k not in skip_args and k != 'url' and k != 'force_refresh'}
            if filtered_kwargs:
                kwargs_str = json.dumps(filtered_kwargs, sort_keys=True, default=str)
                cache_key_parts.append(kwargs_str)
            cache_key_str = ":".join(str(part) for part in cache_key_parts)
            cache_key = hashlib.md5(cache_key_str.encode()).hexdigest()
            full_cache_key = f"{prefix}:{cache_key}"
            if not force_refresh:
                cached_data = script_cache.get(full_cache_key)
                if cached_data:
                    logger.info(f"内存缓存命中: {method_name}", extra={"request_id": trace_key, "cache_key": full_cache_key})
                    return cached_data['result']
            logger.info(f"内存缓存未命中 ({full_cache_key})，执行方法: {method_name}", extra={"request_id": trace_key})
            start_time = time.time()
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            try:
                cache_data = {"result": result, "cached_at": time.time(), "execution_time": execution_time, "url": url}
                script_cache.set(full_cache_key, cache_data, expire_seconds)
                logger.info(f"内存结果已缓存: {method_name}, 耗时: {execution_time:.2f}s", extra={"request_id": trace_key, "cache_key": full_cache_key})
            except Exception as e:
                logger.error(f"内存缓存结果失败: {str(e)}", extra={"request_id": trace_key})
            return result
        return wrapper
    return decorator

# Redis 客户端获取函数 (保持不变，使用 CACHE_REDIS_URL)
_redis_client_cache = None 
def get_redis_client():
    global _redis_client_cache
    if _redis_client_cache is None:
        if not settings.CACHE_REDIS_URL or not isinstance(settings.CACHE_REDIS_URL, str):
            logger.error("CACHE_REDIS_URL 未在配置中设置或类型不正确，无法创建缓存客户端。")
            return None
        try:
            cache_redis_url = settings.CACHE_REDIS_URL
            log_url = cache_redis_url
            try:
                 from urllib.parse import urlparse
                 parsed = urlparse(cache_redis_url)
                 if parsed.password: log_url = cache_redis_url.replace(":" + parsed.password + "@", ":**@")
            except: pass
            logger.info(f"尝试连接到缓存 Redis: {log_url}")
            _redis_client_cache = redis.from_url(cache_redis_url, decode_responses=True)
            _redis_client_cache.ping()
            logger.info(f"已创建并连接到同步 Redis 客户端用于缓存: {log_url}")
        except ImportError:
             logger.error("同步 Redis 客户端 'redis' 未安装！请运行 'pip install redis'")
             _redis_client_cache = None
        except Exception as e:
            logger.error(f"连接到 Redis 缓存失败 ({log_url}): {e}", exc_info=True)
            _redis_client_cache = None
    return _redis_client_cache

# --- 同步 Redis 缓存装饰器 (添加了调试日志) ---
def cache_result_sync(expire_seconds=86400, prefix="celery_cache", skip_args=None):
    """
    [同步] 缓存函数结果到 Redis 的装饰器。
    为 Celery Task 或其他同步函数设计。
    """
    skip_args = skip_args or []

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            redis_client = get_redis_client()
            if not redis_client:
                 logger.warning("Redis 缓存客户端不可用，跳过缓存直接执行函数。")
                 return func(*args, **kwargs)

            force_refresh = kwargs.pop('force_refresh', False)
            method_name = func.__qualname__
            
            # 假设第一个位置参数是主要 Key (e.g., url)
            key_arg = args[0] if args else kwargs.get('url', kwargs.get('id'))
            if key_arg is None: # 如果无法确定主要 key，则不缓存
                 logger.warning(f"无法确定缓存键的关键参数 (args[0] 或 kwargs 'url'/'id')，跳过缓存: {method_name}")
                 return func(*args, **kwargs)
                 
            cache_key_parts = [method_name, str(key_arg)]

            # 过滤并序列化 kwargs
            filtered_kwargs = {
                k: v for k, v in kwargs.items()
                if k not in skip_args and k not in ['url', 'id', 'force_refresh']
            }
            if filtered_kwargs:
                try:
                    kwargs_str = json.dumps(filtered_kwargs, sort_keys=True, default=str)
                    cache_key_parts.append(kwargs_str)
                except TypeError as e:
                     logger.warning(f"无法序列化 kwargs 用于缓存键 ({method_name}): {e}", exc_info=False)
                     pass

            # !! --- 开始添加的调试日志 --- !!
            cache_key_str = ":".join(str(part) for part in cache_key_parts)
            # 打印用于生成哈希的完整字符串
            logger.debug(f"用于生成缓存键的原始字符串 (Pre-hash): '{cache_key_str}'") 
            # 打印参与计算的关键部分，帮助对比
            logger.debug(f"缓存键参数详情: method='{method_name}', key_arg='{str(key_arg)}', filtered_kwargs={filtered_kwargs}")
            # !! --- 结束添加的调试日志 --- !!
            
            hashed_key = hashlib.md5(cache_key_str.encode()).hexdigest()
            full_cache_key = f"{prefix}:{hashed_key}"
            logger.debug(f"生成的完整缓存键 (Full Cache Key): {full_cache_key}") # 打印最终 key
            
            # 检查缓存
            cached_value_str = None
            if not force_refresh:
                try:
                    logger.debug(f"尝试从 Redis 缓存中获取 Key: {full_cache_key}")
                    cached_value_str = redis_client.get(full_cache_key)
                except Exception as redis_e:
                     logger.error(f"从 Redis 获取缓存失败 ({full_cache_key}): {redis_e}", exc_info=True)

                if cached_value_str:
                    try:
                        cached_data = json.loads(cached_value_str)
                        logger.info(f"同步 Redis 缓存命中: {method_name}", extra={"cache_key": full_cache_key})
                        return cached_data # 返回缓存结果
                    except json.JSONDecodeError as json_e:
                         logger.error(f"解析 Redis 缓存数据失败 ({full_cache_key}): {json_e}", exc_info=True)
                         try: redis_client.delete(full_cache_key)
                         except: pass
                    except Exception as parse_e:
                         logger.error(f"处理缓存数据时发生意外错误: {parse_e}", exc_info=True)

            # 缓存未命中或强制刷新
            logger.info(f"同步缓存未命中或强制刷新 ({full_cache_key})，执行方法: {method_name}")
            start_time = time.time()
            try:
                result = func(*args, **kwargs) # 同步执行
                execution_time = time.time() - start_time
                
                # 存储结果到缓存
                should_cache = False
                if isinstance(result, dict) and result.get("status") == "success":
                     should_cache = True

                if should_cache:
                    try:
                        value_to_cache_str = json.dumps(result, default=str)
                        redis_client.setex(full_cache_key, expire_seconds, value_to_cache_str)
                        logger.debug(f"同步结果已缓存: {method_name}, Key: {full_cache_key}, 耗时: {execution_time:.2f}s", extra={"cache_key": full_cache_key, "expire": expire_seconds})
                    except TypeError as json_e:
                         logger.error(f"序列化结果到 JSON 失败 ({method_name})，无法缓存: {json_e}", exc_info=True)
                    except Exception as redis_e:
                         logger.error(f"存储结果到 Redis 缓存失败 ({full_cache_key}): {redis_e}", exc_info=True)
                else:
                     logger.debug(f"结果不适合缓存或标记为不缓存 ({method_name})")
                return result
            except Exception as func_exc:
                 logger.error(f"执行函数 {method_name} 时发生异常，不缓存。", exc_info=True)
                 raise func_exc
        return wrapper
    return decorator