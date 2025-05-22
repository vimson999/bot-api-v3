# bot_api_v1/app/core/cache.py (已添加调试日志)

import functools
import hashlib
import json
import time
from typing import Dict, Any, Tuple, Optional, Union
from datetime import datetime, timedelta
import logging # <-- 添加了顶层导入

import redis # 导入同步 redis 库
import urllib.parse 
from bot_api_v1.app.core.config import settings
from bot_api_v1.app.core.logger import logger # 导入 logger 实例
import redis.asyncio as aioredis

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
def cache_result_sync(expire_seconds=86400, prefix="celery_cache", key_args=None):
    """
    [同步] 缓存函数结果到 Redis 的装饰器。
    为 Celery Task 或其他同步函数设计。
    """
    key_args = key_args or []
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            redis_client = get_redis_client()
            if not redis_client:
                 logger.warning("Redis 缓存客户端不可用，跳过缓存直接执行函数。")
                 return func(*args, **kwargs)

            force_refresh = kwargs.pop('force_refresh', False)
            method_name = func.__qualname__
            
            if key_args is None: # 如果无法确定主要 key，则不缓存
                 logger.warning(f"无法确定缓存键的关键参数 (args[0] 或 kwargs 'url'/'id')，跳过缓存: {method_name}")
                 return func(*args, **kwargs)
                 
            cache_key_parts = [prefix]
            filtered_kwargs = {
                k: v for k, v in kwargs.items()
                if k in key_args
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
            logger.debug(f"缓存键参数详情: prefix='{prefix}', key_args='{str(key_args)}',filtered_kwargs is {filtered_kwargs}")
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




# --- 重构的Redis缓存操作函数 ---
class RedisCache:
    """Redis缓存操作的统一接口类"""
    
    @staticmethod
    def create_key(prefix: str, value: str) -> str:
        """创建缓存键"""
        hashed_key = hashlib.md5(value.encode()).hexdigest()
        return f"{prefix}:{hashed_key}"


    @staticmethod
    def del_key(key: str) -> bool:
        """从Redis中删除指定的缓存键"""
        redis_client = get_redis_client()
        if not redis_client:
            logger.warning("Redis客户端不可用，无法删除缓存")
            return False
        try:
            redis_client.delete(key)
            logger.debug(f"已从Redis中删除缓存: Key={key}")
            return True
        except Exception as e:
            logger.error(f"从Redis删除缓存时发生错误: {e}", exc_info=True)
            return False


    @staticmethod
    def get(key: str) -> Optional[dict]:
        """从Redis获取缓存值并解析JSON"""
        redis_client = get_redis_client()
        if not redis_client:
            logger.warning("Redis客户端不可用，无法获取缓存")
            return None
            
        try:
            value_str = redis_client.get(key)
            if not value_str:
                return None
                
            return json.loads(value_str)
        except json.JSONDecodeError:
            logger.error(f"解析Redis缓存数据失败 ({key})", exc_info=True)
            try: 
                redis_client.delete(key)
            except Exception:
                pass
            return None
        except Exception as e:
            logger.error(f"从Redis获取缓存时发生错误: {e}", exc_info=True)
            return None
    
    @staticmethod
    def set(key: str, value: Union[dict, list], expire_seconds: int = 1800) -> bool:
        """将值存储到Redis缓存"""
        redis_client = get_redis_client()
        if not redis_client:
            logger.warning("Redis客户端不可用，无法设置缓存")
            return False
            
        try:
            value_str = json.dumps(value, default=str)
            redis_client.setex(key, expire_seconds, value_str)
            logger.debug(f"数据已缓存: Key={key}, 过期时间={expire_seconds}秒")
            return True
        except TypeError as e:
            logger.error(f"序列化数据到JSON失败: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"存储数据到Redis缓存失败 ({key}): {e}", exc_info=True)
            return False

# def get_from_sync_cache(key):
#     redis_client = get_redis_client()
#     return redis_client.get(key)

# def create_key(prefix:str, original_url:str):
#     hashed_key = hashlib.md5(original_url.encode()).hexdigest()
#     full_cache_key = f"{prefix}:{hashed_key}"
#     return full_cache_key

# def create_task_b_result_sync_cache(url:str,task_b_final_result:dict):
#     redis_client = get_redis_client()
#     full_cache_key = create_key("get_task_b_result",url)
#     expire_seconds = 60 * 30
    
#     value_to_cache_str = json.dumps(task_b_final_result, default=str)
#     redis_client.setex(full_cache_key, expire_seconds, value_to_cache_str)


# --- 重构的缓存操作函数 ---
def get_task_result_from_cache(url: str, prefix: str = "get_task_b_result") -> Optional[dict]:
    """从缓存获取任务结果"""
    cache_key = RedisCache.create_key(prefix, url)
    logger.debug(f"尝试从缓存获取任务结果: {cache_key}")
    return RedisCache.get(cache_key)

def save_task_result_to_cache(url: str, result: dict, prefix: str = "get_task_b_result", expire_seconds: int = 1800) -> bool:
    """保存任务结果到缓存"""
    if not isinstance(result, dict):
        logger.warning(f"无法缓存非字典类型的结果: {type(result)}")
        return False
        
    cache_key = RedisCache.create_key(prefix, url)
    logger.debug(f"保存任务结果到缓存: {cache_key}")
    return RedisCache.set(cache_key, result, expire_seconds)

# 为了向后兼容，保留原有函数但使用新实现
def create_key(prefix: str, original_url: str) -> str:
    return RedisCache.create_key(prefix, original_url)

def get_from_sync_cache(key: str) -> Optional[dict]:
    return RedisCache.get(key)

def create_task_b_result_sync_cache(url: str, task_b_final_result: dict, expire_seconds: int = 1800) -> bool:
    return save_task_result_to_cache(url, task_b_final_result, expire_seconds=expire_seconds)


_aioredis_client_cache = None
async def get_aioredis_client():
    global _aioredis_client_cache
    if _aioredis_client_cache is not None:
        return _aioredis_client_cache
    from bot_api_v1.app.core.config import settings
    if not hasattr(settings, "CACHE_REDIS_URL") or not settings.CACHE_REDIS_URL:
        logging.error("CACHE_REDIS_URL 未配置，无法创建异步 Redis 客户端。")
        return None
    _aioredis_client_cache = aioredis.from_url(settings.CACHE_REDIS_URL, decode_responses=True)
    return _aioredis_client_cache

# 异步 Redis 缓存装饰器
def async_cache_result(expire_seconds=600, prefix="async_cache", key_args=None):
    key_args = key_args or []
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            redis_client = await get_aioredis_client()
            if not redis_client:
                return await func(*args, **kwargs)
            force_refresh = kwargs.pop('force_refresh', False)
            method_name = func.__qualname__
            cache_key_parts = [prefix, method_name]
            # 生成缓存 key
            if key_args:
                filtered_kwargs = {k: v for k, v in kwargs.items() if k in key_args}
                if filtered_kwargs:
                    try:
                        kwargs_str = json.dumps(filtered_kwargs, sort_keys=True, default=str)
                        cache_key_parts.append(kwargs_str)
                    except Exception:
                        pass
            cache_key_str = ":".join(str(part) for part in cache_key_parts)
            hashed_key = hashlib.md5(cache_key_str.encode()).hexdigest()
            full_cache_key = f"{prefix}:{hashed_key}"
            # 查询缓存
            if not force_refresh:
                try:
                    cached_value_str = await redis_client.get(full_cache_key)
                    if cached_value_str:
                        return json.loads(cached_value_str)
                except Exception:
                    pass
            # 未命中缓存
            result = await func(*args, **kwargs)
            try:
                value_to_cache_str = json.dumps(result, default=str)
                await redis_client.setex(full_cache_key, expire_seconds, value_to_cache_str)
            except Exception:
                pass
            return result
        return wrapper
    return decorator