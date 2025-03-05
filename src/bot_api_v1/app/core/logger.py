import os
import logging
import json
from pathlib import Path
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

load_dotenv()

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

    # 文件处理器
    file_handler = RotatingFileHandler(
        filename=LOG_DIR / f"api_{os.getpid()}.log",
        maxBytes=1024 * 1024 * 10,
        backupCount=100,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    
    # 添加控制台处理器，便于调试
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info("Logger initialization completed", extra={"request_id": "system"})
    return logger

# 延迟初始化，建议在 main.py 中调用
logger = setup_logger()
