#logger.py
import os
import logging
import json
from pathlib import Path
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

load_dotenv()


    # logger.py
class RequestFormatter(logging.Formatter):
    def format(self, record):
        # 处理缺失字段
        if not hasattr(record, 'request_id'):
            record.request_id = 'system'  # 设置默认值
        if not hasattr(record, 'headers'):
            record.headers = '{}'
        elif isinstance(record.headers, dict):
            record.headers = json.dumps(record.headers, ensure_ascii=False)
        return super().format(record)
    
    

def setup_logger(name: str = "api"):
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # 日志格式
    formatter = RequestFormatter(
        '[%(asctime)s] [%(request_id)s] %(levelname)s in %(module)s: %(message)s | HEADERS=%(headers)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 文件处理器
    LOG_DIR = Path(__file__).parent.parent / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    
    file_handler = RotatingFileHandler(
        filename=LOG_DIR / "api.log",
        maxBytes=1024 * 1024 * 10,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.terminator = '\n'  # 确保每条日志独立成行

    logger.addHandler(file_handler)
    
    # 初始化日志
    logger.info("Logger initialization completed", extra={
        "request_id": "system",
        "headers": {}
    })
    
    return logger

logger = setup_logger()