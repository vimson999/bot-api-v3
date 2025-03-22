"""
增强版Prometheus监控模块

提供更全面的API服务监控指标
"""
from prometheus_client import Counter, Histogram, Gauge, Info, Summary
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from prometheus_fastapi_instrumentator.metrics import Info as MetricInfo
import time
import psutil
import platform
import os
from fastapi import FastAPI, Request
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)

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
    "api_memory_usage_bytes", 
    "内存使用字节数",
    ["type"]  # used, free, total
)

MEMORY_PERCENT = Gauge(
    "api_memory_usage_percent", 
    "内存使用百分比"
)

DISK_USAGE = Gauge(
    "api_disk_usage_bytes",
    "磁盘使用字节数",
    ["path", "type"]  # used, free, total
)

DISK_PERCENT = Gauge(
    "api_disk_usage_percent",
    "磁盘使用百分比",
    ["path"]
)

OPEN_FILES = Gauge(
    "api_open_files_count", 
    "打开的文件句柄数"
)

DB_POOL_USAGE = Gauge(
    "api_db_pool_usage",
    "数据库连接池使用情况",
    ["type"]  # used, available, total, overflow
)

DB_QUERY_DURATION = Histogram(
    "api_db_query_duration_seconds",
    "数据库查询执行时间",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

DB_QUERY_COUNT = Counter(
    "api_db_query_count_total",
    "数据库查询总数",
    ["operation", "success"]
)

TASK_COUNT = Gauge(
    "api_task_count",
    "任务数量",
    ["status", "type"]  # running, completed, failed, cancelled, etc.
)

SERVICE_UPTIME = Gauge(
    "api_service_uptime_seconds",
    "服务运行时间（秒）"
)

# API业务指标
MEDIA_EXTRACT_COUNT = Counter(
    "api_media_extract_total",
    "媒体内容提取请求总数",
    ["platform", "status"]  # douyin, xiaohongshu, etc.
)

MEDIA_EXTRACT_DURATION = Histogram(
    "api_media_extract_duration_seconds",
    "媒体内容提取处理时间",
    ["platform"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
)

SCRIPT_TRANSCRIBE_COUNT = Counter(
    "api_script_transcribe_total",
    "音频转写请求总数",
    ["status"]  # success, error
)

SCRIPT_TRANSCRIBE_DURATION = Histogram(
    "api_script_transcribe_duration_seconds",
    "音频转写处理时间",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0)
)

def initialize_system_metrics():
    """初始化系统信息指标"""
    system_info = {
        "os": platform.system(),
        "python_version": platform.python_version(),
        "processor": platform.processor(),
        "hostname": platform.node(),
        "cpu_count": psutil.cpu_count(logical=True),
        "physical_cpu_count": psutil.cpu_count(logical=False)
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
        excluded_handlers=["/metrics", "/api/health", "/api/monitoring/health/detailed"],
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
            name="api_db_pool_metrics",
            description="数据库连接池大小和使用情况",
            metric_namespace="db",
        )
    )
    def db_pool_metrics(metric: MetricInfo):
        from bot_api_v1.app.db.session import engine
        
        def instrumentation(request, response, latency, scope):
            try:
                if hasattr(engine, "pool"):
                    pool = engine.pool
                    if hasattr(pool, "checkedout"):
                        DB_POOL_USAGE.labels(type="used").set(pool.checkedout())
                    if hasattr(pool, "checkedin"):
                        DB_POOL_USAGE.labels(type="available").set(pool.checkedin())
                    if hasattr(pool, "size"):
                        DB_POOL_USAGE.labels(type="total").set(pool.size())
                    if hasattr(pool, "overflow"):
                        DB_POOL_USAGE.labels(type="overflow").set(pool.overflow())
            except Exception as e:
                logger.warning(f"收集数据库连接池指标失败: {str(e)}")
        
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
                # 更新CPU指标
                CPU_USAGE.set(psutil.cpu_percent(interval=None))
                
                # 更新内存指标
                mem = psutil.virtual_memory()
                MEMORY_USAGE.labels(type="total").set(mem.total)
                MEMORY_USAGE.labels(type="used").set(mem.used)
                MEMORY_USAGE.labels(type="free").set(mem.available)
                MEMORY_PERCENT.set(mem.percent)
                
                # 更新磁盘指标
                for partition in psutil.disk_partitions():
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        path = partition.mountpoint
                        DISK_USAGE.labels(path=path, type="total").set(usage.total)
                        DISK_USAGE.labels(path=path, type="used").set(usage.used)
                        DISK_USAGE.labels(path=path, type="free").set(usage.free)
                        DISK_PERCENT.labels(path=path).set(usage.percent)
                    except (PermissionError, OSError):
                        # 跳过无法访问的挂载点
                        continue
                
                # 更新文件句柄指标
                OPEN_FILES.set(len(psutil.Process().open_files()))
                
                # 更新服务运行时间
                if hasattr(request.app.state, "startup_time"):
                    uptime = time.time() - request.app.state.startup_time
                    SERVICE_UPTIME.set(uptime)
            except Exception as e:
                logger.warning(f"收集系统指标失败: {str(e)}")
        
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
    
    # 添加自定义任务指标
    @instrumentator.add(
        MetricInfo(
            name="api_task_metrics",
            description="异步任务统计",
            metric_namespace="tasks",
        )
    )
    def task_metrics(metric: MetricInfo):
        def instrumentation(request, response, latency, scope):
            try:
                # 从全局任务管理中获取统计数据
                from bot_api_v1.app.tasks.base import get_task_statistics
                
                stats = get_task_statistics()
                
                # 更新运行状态计数
                if "status_counts" in stats:
                    for status, count in stats["status_counts"].items():
                        for task_type, type_count in stats.get("type_counts", {}).items():
                            # 由于我们没有具体状态和类型的组合数据，这里使用估算
                            # 实际生产中应该收集更精确的数据
                            estimated_count = count * (type_count / stats["total_tasks"]) if stats["total_tasks"] > 0 else 0
                            TASK_COUNT.labels(status=status, type=task_type).set(estimated_count)
            except Exception as e:
                logger.warning(f"收集任务指标失败: {str(e)}")
        
        return instrumentation
    
    # 添加业务指标
    @instrumentator.add(
        MetricInfo(
            name="api_business_metrics",
            description="业务指标",
            metric_namespace="business",
        )
    )
    def business_metrics(metric: MetricInfo):
        def instrumentation(request, response, latency, scope):
            try:
                # 检查路径以决定记录哪种业务指标
                path = scope["path"] if "path" in scope else ""
                method = scope["method"] if "method" in scope else ""
                
                # 仅处理POST请求
                if method != "POST":
                    return
                
                # 媒体提取指标
                if "/api/media/extract" in path:
                    # 解析JSON响应获取平台
                    try:
                        resp_json = response.body_iterator
                        platform = "unknown"  # 默认平台
                        
                        # TODO: 实际实现中需要解析响应以获取平台名称
                        
                        # 记录请求计数和耗时
                        status = "success" if response.status_code < 400 else "error"
                        MEDIA_EXTRACT_COUNT.labels(platform=platform, status=status).inc()
                        MEDIA_EXTRACT_DURATION.labels(platform=platform).observe(latency)
                    except Exception as e:
                        logger.warning(f"无法解析媒体提取响应: {str(e)}")
                
                # 音频转写指标
                elif "/api/script/transcribe" in path:
                    status = "success" if response.status_code < 400 else "error"
                    SCRIPT_TRANSCRIBE_COUNT.labels(status=status).inc()
                    SCRIPT_TRANSCRIBE_DURATION.observe(latency)
            except Exception as e:
                logger.warning(f"收集业务指标失败: {str(e)}")
        
        return instrumentation
    
    # 初始化并安装到 FastAPI 应用
    instrumentator.instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=include_in_schema,
        tags=["监控"],
        summary="Prometheus 指标",
        description="导出 Prometheus 格式的监控指标，用于监控系统采集",
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
    async def add_metrics(request: Request, call_next):
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

def collect_db_metrics():
    """收集数据库指标的辅助函数，可用于周期性收集"""
    try:
        from bot_api_v1.app.db.session import engine
        if hasattr(engine, "pool"):
            pool = engine.pool
            if hasattr(pool, "checkedout"):
                DB_POOL_USAGE.labels(type="used").set(pool.checkedout())
            if hasattr(pool, "checkedin"):
                DB_POOL_USAGE.labels(type="available").set(pool.checkedin())
            if hasattr(pool, "size"):
                DB_POOL_USAGE.labels(type="total").set(pool.size())
            if hasattr(pool, "overflow"):
                DB_POOL_USAGE.labels(type="overflow").set(pool.overflow())
    except Exception as e:
        logger.warning(f"收集数据库指标失败: {str(e)}")

def collect_system_metrics():
    """收集系统指标的辅助函数，可用于周期性收集"""
    try:
        # 更新CPU指标
        CPU_USAGE.set(psutil.cpu_percent(interval=0.1))
        
        # 更新内存指标
        mem = psutil.virtual_memory()
        MEMORY_USAGE.labels(type="total").set(mem.total)
        MEMORY_USAGE.labels(type="used").set(mem.used)
        MEMORY_USAGE.labels(type="free").set(mem.available)
        MEMORY_PERCENT.set(mem.percent)
        
        # 更新磁盘指标 - 仅主分区
        try:
            root_path = "/"
            usage = psutil.disk_usage(root_path)
            DISK_USAGE.labels(path=root_path, type="total").set(usage.total)
            DISK_USAGE.labels(path=root_path, type="used").set(usage.used)
            DISK_USAGE.labels(path=root_path, type="free").set(usage.free)
            DISK_PERCENT.labels(path=root_path).set(usage.percent)
        except Exception as e:
            logger.warning(f"收集磁盘指标失败: {str(e)}")
        
        # 更新文件句柄指标
        try:
            OPEN_FILES.set(len(psutil.Process().open_files()))
        except Exception as e:
            logger.warning(f"收集文件句柄指标失败: {str(e)}")
    except Exception as e:
        logger.warning(f"收集系统指标失败: {str(e)}")

def collect_task_metrics():
    """收集任务指标的辅助函数，可用于周期性收集"""
    try:
        from bot_api_v1.app.tasks.base import get_task_statistics
        
        stats = get_task_statistics()
        
        # 更新运行状态计数
        if "status_counts" in stats:
            for status, count in stats["status_counts"].items():
                for task_type, type_count in stats.get("type_counts", {}).items():
                    # 由于我们没有具体状态和类型的组合数据，这里使用估算
                    estimated_count = count * (type_count / stats["total_tasks"]) if stats["total_tasks"] > 0 else 0
                    TASK_COUNT.labels(status=status, type=task_type).set(estimated_count)
    except Exception as e:
        logger.warning(f"收集任务指标失败: {str(e)}")

def start_system_metrics_collector(app: FastAPI):
    """
    启动系统指标收集器
    
    Args:
        app: FastAPI 应用
    """
    import asyncio
    
    async def collect_metrics_periodically():
        startup_time = time.time()
        
        while True:
            try:
                # 收集系统指标
                collect_system_metrics()
                
                # 收集数据库指标
                collect_db_metrics()
                
                # 收集任务指标
                collect_task_metrics()
                
                # 更新服务运行时间
                uptime = time.time() - startup_time
                SERVICE_UPTIME.set(uptime)
                
                # 从应用状态中获取数据库指标(如果有)
                if hasattr(app.state, "db_pool_size"):
                    DB_POOL_USAGE.labels(type="total").set(app.state.db_pool_size)
                if hasattr(app.state, "db_pool_used"):
                    DB_POOL_USAGE.labels(type="used").set(app.state.db_pool_used)
                
            except Exception as e:
                logger.warning(f"收集周期性指标失败: {str(e)}")
            
            # 每15秒收集一次
            await asyncio.sleep(15)
    
    # 启动任务
    @app.on_event("startup")
    async def start_metrics_collection():
        asyncio.create_task(collect_metrics_periodically())