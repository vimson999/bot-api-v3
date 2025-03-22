"""
Prometheus 监控模块

提供 Prometheus 指标收集和导出功能，用于监控API服务的性能和健康状况。
"""
from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from prometheus_fastapi_instrumentator.metrics import Info as MetricInfo
import time
import psutil
import platform
from fastapi import FastAPI
from typing import Callable

# 全局指标
REQUEST_COUNT = Counter(
    "api_requests_total", 
    "计数所有传入的请求",
    ["method", "endpoint", "status_code"]
)

REQUEST_LATENCY = Histogram(
    "api_request_latency_seconds",
    "HTTP请求处理时间（秒）",
    ["method", "endpoint", "status_code"],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, float("inf")),
)

EXCEPTIONS_COUNT = Counter(
    "api_exceptions_total",
    "抛出的异常总数",
    ["method", "endpoint", "exception_type"]
)

ACTIVE_REQUESTS = Gauge(
    "api_active_requests", 
    "当前活跃的请求数",
    ["method", "endpoint"]
)

SYSTEM_INFO = Info(
    "api_system_info", 
    "系统信息"
)

CPU_USAGE = Gauge(
    "api_cpu_usage_percent", 
    "CPU使用率"
)

MEMORY_USAGE = Gauge(
    "api_memory_usage_percent", 
    "内存使用率"
)

OPEN_FILES = Gauge(
    "api_open_files_count", 
    "打开的文件句柄数"
)

DB_POOL_USAGE = Gauge(
    "api_db_pool_usage",
    "数据库连接池使用情况",
    ["type"]
)

def initialize_system_metrics():
    """初始化系统信息指标"""
    system_info = {
        "os": platform.system(),
        "python_version": platform.python_version(),
        "processor": platform.processor(),
        "hostname": platform.node()
    }
    SYSTEM_INFO.info(system_info)

def setup_metrics(app: FastAPI, app_name: str = "bot_api", include_in_schema: bool = True):
    """
    设置 Prometheus 指标收集
    
    Args:
        app: FastAPI应用实例
        app_name: 应用名称，用于指标标签
        include_in_schema: 是否在API文档中包含监控端点
    """
    # 初始化系统信息
    initialize_system_metrics()
    
    # 创建和配置Instrumentator实例
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics"],
        inprogress_name="api_requests_inprogress",
        inprogress_labels=["method", "handler"]
    )
    
    # 添加默认指标
    instrumentator.add(
        metrics.request_size(
            metric_name="api_request_size_bytes",
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )
    
    instrumentator.add(
        metrics.response_size(
            metric_name="api_response_size_bytes",
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )
    
    instrumentator.add(
        metrics.latency(
            metric_name="api_request_duration_seconds",
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )
    
    # 添加自定义数据库连接池指标
    @instrumentator.add(
        MetricInfo(
            name="api_db_pool_size",
            description="数据库连接池大小和使用情况",
            metric_namespace="db",
        )
    )
    def db_pool_metrics(metric: MetricInfo):
        from bot_api_v1.app.db.session import engine
        
        def instrumentation(request, response, latency, scope):
            try:
                if hasattr(engine, "pool"):
                    DB_POOL_USAGE.labels(type="used").set(engine.pool.checkedout())
                    DB_POOL_USAGE.labels(type="available").set(engine.pool.size())
                    DB_POOL_USAGE.labels(type="overflow").set(engine.pool.overflow())
            except Exception:
                pass  # 忽略指标收集错误
        
        return instrumentation
    
    # 添加自定义系统指标
    @instrumentator.add(
        MetricInfo(
            name="api_system_metrics",
            description="系统指标，如 CPU 和内存使用率",
            metric_namespace="system",
        )
    )
    def system_metrics(metric: MetricInfo):
        def instrumentation(request, response, latency, scope):
            try:
                # 更新系统指标
                CPU_USAGE.set(psutil.cpu_percent(interval=None))
                MEMORY_USAGE.set(psutil.virtual_memory().percent)
                OPEN_FILES.set(len(psutil.Process().open_files()))
            except Exception:
                pass  # 忽略指标收集错误
        
        return instrumentation
    
    # 添加自定义异常指标
    @instrumentator.add(
        MetricInfo(
            name="api_exceptions",
            description="API 异常统计",
            metric_namespace="exceptions",
        )
    )
    def exception_metrics(metric: MetricInfo):
        def instrumentation(request, response, latency, scope):
            if response.status_code >= 500:
                endpoint = scope["route"].path if "route" in scope else scope["path"]
                method = scope["method"]
                EXCEPTIONS_COUNT.labels(
                    method=method, 
                    endpoint=endpoint, 
                    exception_type="server_error"
                ).inc()
            elif response.status_code >= 400:
                endpoint = scope["route"].path if "route" in scope else scope["path"]
                method = scope["method"]
                EXCEPTIONS_COUNT.labels(
                    method=method, 
                    endpoint=endpoint, 
                    exception_type="client_error"
                ).inc()
        
        return instrumentation
    
    # 初始化并安装到 FastAPI 应用
    instrumentator.instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=include_in_schema,
        tags=["监控"],
        summary="Prometheus 指标",
        description="导出 Prometheus 格式的监控指标",
    )
    
    return instrumentator

# 应用中间件，用于记录自定义指标
def metrics_middleware(app: FastAPI):
    """
    创建一个记录指标的中间件
    
    Args:
        app: FastAPI 应用
    """
    @app.middleware("http")
    async def add_metrics(request, call_next):
        # 提取请求路径和方法
        path = request.url.path
        method = request.method
        
        # 排除监控端点本身
        if path == "/metrics":
            return await call_next(request)
        
        # 增加活跃请求计数
        ACTIVE_REQUESTS.labels(method=method, endpoint=path).inc()
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # 记录请求数
            REQUEST_COUNT.labels(
                method=method,
                endpoint=path,
                status_code=response.status_code
            ).inc()
            
            # 记录延迟
            REQUEST_LATENCY.labels(
                method=method,
                endpoint=path,
                status_code=response.status_code
            ).observe(time.time() - start_time)
            
            return response
            
        except Exception as e:
            # 记录异常
            EXCEPTIONS_COUNT.labels(
                method=method,
                endpoint=path,
                exception_type=type(e).__name__
            ).inc()
            raise
        finally:
            # 无论成功或失败，减少活跃请求计数
            ACTIVE_REQUESTS.labels(method=method, endpoint=path).dec()
    
    return add_metrics

# 后台任务，用于收集周期性的系统指标
def start_system_metrics_collector(app: FastAPI):
    """
    启动系统指标收集器
    
    Args:
        app: FastAPI 应用
    """
    import asyncio
    
    async def collect_system_metrics():
        while True:
            try:
                # 更新系统指标
                CPU_USAGE.set(psutil.cpu_percent(interval=1))
                MEMORY_USAGE.set(psutil.virtual_memory().percent)
                OPEN_FILES.set(len(psutil.Process().open_files()))
                
                # 从应用状态中获取数据库指标(如果有)
                if hasattr(app.state, "db_pool_size"):
                    DB_POOL_USAGE.labels(type="total").set(app.state.db_pool_size)
                if hasattr(app.state, "db_pool_used"):
                    DB_POOL_USAGE.labels(type="used").set(app.state.db_pool_used)
                
            except Exception:
                # 忽略指标收集错误
                pass
            
            # 每15秒收集一次
            await asyncio.sleep(15)
    
    # 启动任务
    @app.on_event("startup")
    async def start_metrics_collection():
        asyncio.create_task(collect_system_metrics())