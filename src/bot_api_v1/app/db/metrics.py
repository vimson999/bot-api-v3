"""
数据库监控指标收集模块
"""
from prometheus_client import Counter, Histogram, Gauge, Summary
import time
import functools
from typing import Callable, Any

# 数据库指标
DB_QUERY_COUNT = Counter(
    "api_db_queries_total", 
    "执行的查询总数",
    ["operation", "success"]
)

DB_QUERY_LATENCY = Histogram(
    "api_db_query_latency_seconds",
    "数据库查询执行时间（秒）",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0)
)

DB_CONNECTION_POOL = Gauge(
    "api_db_connection_pool",
    "数据库连接池状态",
    ["state"]  # 'in_use', 'available', 'overflow'
)

TRANSACTION_COUNT = Counter(
    "api_db_transactions_total",
    "事务总数",
    ["operation", "success"]  # 'begin', 'commit', 'rollback'
)

def instrument_async_session(method: Callable) -> Callable:
    """
    一个装饰器，用于监控异步会话方法的性能
    
    Args:
        method: 要监控的异步会话方法
        
    Returns:
        装饰后的方法，具有指标收集功能
    """
    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        method_name = method.__name__
        operation = "query" if method_name == "execute" else method_name
        
        # 记录开始时间
        start_time = time.time()
        
        try:
            # 执行原始方法
            result = await method(self, *args, **kwargs)
            
            # 记录成功查询
            DB_QUERY_COUNT.labels(
                operation=operation,
                success="true"
            ).inc()
            
            return result
        except Exception as e:
            # 记录失败查询
            DB_QUERY_COUNT.labels(
                operation=operation,
                success="false"
            ).inc()
            
            # 重新抛出异常
            raise
        finally:
            # 记录查询延迟
            execution_time = time.time() - start_time
            DB_QUERY_LATENCY.labels(
                operation=operation
            ).observe(execution_time)
            
            # 更新连接池指标（如果有连接池信息）
            if hasattr(self, 'get_bind') and hasattr(self.get_bind(), 'pool'):
                pool = self.get_bind().pool
                if hasattr(pool, 'checkedout'):
                    DB_CONNECTION_POOL.labels(state="in_use").set(pool.checkedout())
                if hasattr(pool, 'checkedin'):
                    DB_CONNECTION_POOL.labels(state="available").set(pool.checkedin())
                if hasattr(pool, 'overflow'):
                    DB_CONNECTION_POOL.labels(state="overflow").set(pool.overflow())
    
    return wrapper

def instrument_transaction(method: Callable) -> Callable:
    """
    一个装饰器，用于监控事务操作
    
    Args:
        method: 要监控的事务方法
        
    Returns:
        装饰后的方法，具有指标收集功能
    """
    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        method_name = method.__name__
        
        try:
            # 执行原始方法
            result = await method(self, *args, **kwargs)
            
            # 记录成功的事务操作
            TRANSACTION_COUNT.labels(
                operation=method_name,
                success="true"
            ).inc()
            
            return result
        except Exception as e:
            # 记录失败的事务操作
            TRANSACTION_COUNT.labels(
                operation=method_name,
                success="false"
            ).inc()
            
            # 重新抛出异常
            raise
    
    return wrapper

def instrument_engine_connect(method: Callable) -> Callable:
    """
    装饰数据库引擎的connect方法，用于跟踪连接创建
    
    Args:
        method: 引擎的connect方法
        
    Returns:
        装饰后的方法
    """
    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        connect_metric = Counter(
            "api_db_connections_created_total", 
            "创建的数据库连接总数"
        )
        
        try:
            # 执行原始方法
            result = await method(self, *args, **kwargs)
            
            # 记录成功的连接创建
            connect_metric.inc()
            
            # 更新连接池统计信息
            if hasattr(self, 'pool'):
                DB_CONNECTION_POOL.labels(state="total").set(
                    getattr(self.pool, 'size', lambda: 0)()
                )
            
            return result
        except Exception as e:
            # 记录失败的连接尝试
            Counter(
                "api_db_connection_errors_total",
                "数据库连接错误总数",
                ["error_type"]
            ).labels(error_type=type(e).__name__).inc()
            
            # 重新抛出异常
            raise
    
    return wrapper

def patch_sqlalchemy_metrics():
    """
    通过猴子补丁的方式为SQLAlchemy添加指标收集功能
    """
    from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine
    
    # 为异步会话添加指标
    original_execute = AsyncSession.execute
    AsyncSession.execute = instrument_async_session(original_execute)
    
    original_commit = AsyncSession.commit
    AsyncSession.commit = instrument_transaction(original_commit)
    
    original_rollback = AsyncSession.rollback
    AsyncSession.rollback = instrument_transaction(original_rollback)
    
    # 为异步引擎添加指标
    if hasattr(AsyncEngine, 'connect'):
        original_connect = AsyncEngine.connect
        AsyncEngine.connect = instrument_engine_connect(original_connect)