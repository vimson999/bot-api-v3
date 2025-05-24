# bot_api_v1/app/tasks/celery_app.py (已更新)
import os
import time
from datetime import datetime
import sys
from celery.signals import worker_process_init, worker_process_shutdown
from celery.schedules import crontab


from celery import Celery
# !! 导入 config 中的 settings 对象 !!
# 确保导入路径正确
try:
     from bot_api_v1.app.core.config import settings 
except ImportError:
     # Fallback 或提示错误
     print("错误：无法从 bot_api_v1.app.core.config 导入 settings！请检查路径和 __init__.py 文件。")
     # 或者尝试绝对路径（如果你的项目结构和运行方式支持）
     # from src.bot_api_v1.app.core.config import settings
     raise # 抛出异常阻止继续

# 创建 Celery 应用实例
# 使用 settings 中的配置项
celery_app = Celery(
    settings.PROJECT_NAME, # 使用项目名称
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        'bot_api_v1.app.tasks.celery_tasks' # !! 保持任务模块路径 !!
        ]
)

# 使用 settings 对象更新 Celery 配置
celery_app.conf.update(
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    result_serializer=settings.CELERY_RESULT_SERIALIZER,
    accept_content=settings.CELERY_ACCEPT_CONTENT,
    timezone=settings.TIMEZONE, # 使用 settings 中的时区
    enable_utc=settings.CELERY_ENABLE_UTC,
    result_expires=settings.CELERY_RESULT_EXPIRES,
    broker_connection_retry_on_startup=settings.CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP,
    # 可以添加更多来自 settings 的配置项
    # worker_concurrency = settings.CELERY_WORKER_CONCURRENCY, # 例如设置并发数
)

# # if __name__ == '__main__' 部分可以保持不变，用于本地测试启动 Worker
# if __name__ == '__main__':
#     celery_app.start(['worker', '--loglevel=info'])

# 在celery_app.py中添加
@worker_process_init.connect
def init_worker_process(sender=None, **kwargs):
    """当Celery工作进程启动时初始化日志处理器"""
    print(f"[{datetime.now()}] INFO: Celery工作进程 {os.getpid()} 启动，初始化日志处理器")
    # 可以在这里进行一些初始化工作

@worker_process_shutdown.connect
def shutdown_worker_process(sender=None, **kwargs):
    """当Celery工作进程关闭时刷新日志缓冲区"""
    from bot_api_v1.app.core.logger import CeleryLogHandler
    print(f"[{datetime.now()}] INFO: Celery工作进程 {os.getpid()} 关闭，刷新日志缓冲区")
    try:
        CeleryLogHandler._flush_logs()
    except Exception as e:
        print(f"[{datetime.now()}] ERROR: 工作进程关闭时刷新日志失败: {e}", file=sys.stderr)




celery_app.conf.beat_schedule = {
    'daily-video-update-at-noon': {
        'task': 'tasks.daily_video_data_update_celery', # 任务的名称
        'schedule': crontab(hour=1, minute=0),     # 每天中午12:00执行
        # 'args': (arg1, arg2), # 如果任务需要参数
    },
    'daily-kol-update-at-one-am': {
        'task': 'tasks.daily_kol_data_update_celery',
        'schedule': crontab(hour=2, minute=0),      # 每天凌晨1:00执行
    },
    # 您可以添加更多的定时任务
}
celery_app.conf.timezone = settings.TIMEZONE # 确保时区正确