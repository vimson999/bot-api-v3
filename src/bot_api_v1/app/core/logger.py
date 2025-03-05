import os
import logging
import json
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
import gzip
import shutil
from dotenv import load_dotenv

load_dotenv()

# 自定义GZip压缩旋转器
class GZipRotator:
    def __call__(self, source, dest):
        with open(source, 'rb') as f_in:
            with gzip.open(f"{dest}.gz", 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)  # 删除未压缩的原始文件

class RequestFormatter(logging.Formatter):
    def format(self, record):
        # 设置缺省值
        if not hasattr(record, 'request_id'):
            record.request_id = 'system'
        
        # 处理 headers        
        if hasattr(record, 'headers'):
            # 尝试将 headers 序列化为 JSON
            try:
                if isinstance(record.headers, dict):
                    record.headers = json.dumps(record.headers, ensure_ascii=False)
                elif isinstance(record.headers, str):
                    # 如果已经是字符串，检查是否是有效的 JSON
                    try:
                        json.loads(record.headers)
                    except:
                        record.headers = '{"error": "Invalid JSON string"}'
                else:
                    record.headers = '{"error": "Headers is neither dict nor string"}'
            except:
                record.headers = '{"error": "Serialization failed"}'
        else:
            record.headers = '{}'
            
        # 添加格式化内容并添加两个空行
        return super().format(record) + "\n\n"

def setup_logger(name: str = "api"):
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # 防止重复日志
    if logger.handlers:
        return logger

    if "LOG_LEVEL" not in os.environ:
        print("LOG_LEVEL not set, using default 'INFO'")

    formatter = RequestFormatter(
        '[%(asctime)s] [%(request_id)s] %(levelname)s in %(module)s: %(message)s | HEADERS=%(headers)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 设置日志目录
    LOG_DIR = Path(os.getenv("LOG_DIR", Path(__file__).parent.parent / "logs"))
    try:
        LOG_DIR.mkdir(exist_ok=True)
    except Exception as e:
        print(f"Failed to create log directory: {e}")
        raise

    # 基于时间的文件处理器，每天午夜轮转
    file_handler = TimedRotatingFileHandler(
        filename=LOG_DIR / "api.log",
        when='midnight',        # 每天午夜创建新文件
        interval=1,             # 时间间隔为1天
        backupCount=30,         # 保留30天的日志
        encoding="utf-8",
        utc=True                # 使用UTC时间，避免时区问题
    )
    
    # 设置文件名后缀格式为日期
    file_handler.suffix = "%Y-%m-%d"
    file_handler.extMatch = r"^\d{4}-\d{2}-\d{2}$"
    file_handler.setFormatter(formatter)
    
    # 使用GZip压缩旋转器，节省空间
    file_handler.rotator = GZipRotator()
    
    # 添加处理器
    logger.addHandler(file_handler)
    
    # 生产环境通常不需要控制台输出，但可以根据环境变量决定
    if os.getenv("ENVIRONMENT", "production").lower() != "production":
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    logger.info("Logger initialization completed", extra={"request_id": "system"})
    return logger

# 延迟初始化
logger = setup_logger()
