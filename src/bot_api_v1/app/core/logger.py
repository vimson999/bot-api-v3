import os
import logging
import json
from pathlib import Path
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

load_dotenv()

class RequestFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, 'request_id'):
            record.request_id = 'system'
        if not hasattr(record, 'headers'):
            record.headers = '{}'
        elif not isinstance(record.headers, dict):
            record.headers = '{"error": "Invalid headers type"}'
        else:
            record.headers = json.dumps(record.headers, ensure_ascii=False)
        return super().format(record)

class SecurityFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'headers') and isinstance(record.headers, dict):
            record.headers = {k: '***' if k.lower() in ['authorization', 'cookie'] else v 
                              for k, v in record.headers.items()}
        return True

def setup_logger(name: str = "api"):
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    if "LOG_LEVEL" not in os.environ:
        logger.warning("LOG_LEVEL not set, using default 'INFO'")

    formatter = RequestFormatter(
        '[%(asctime)s] [%(request_id)s] %(levelname)s in %(module)s: %(message)s | HEADERS=%(headers)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    LOG_DIR = Path(os.getenv("LOG_DIR", Path(__file__).parent.parent / "logs"))
    try:
        LOG_DIR.mkdir(exist_ok=True)
    except Exception as e:
        print(f"Failed to create log directory: {e}")
        raise

    file_handler = RotatingFileHandler(
        filename=LOG_DIR / f"api_{os.getpid()}.log",
        maxBytes=1024 * 1024 * 10,
        backupCount=50,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SecurityFilter())

    logger.addHandler(file_handler)
    logger.info("Logger initialization completed", extra={"request_id": "system", "headers": {}})
    return logger

# 延迟初始化，建议在 main.py 中调用
logger = setup_logger()