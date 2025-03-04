#dependencies.py
from sqlalchemy.orm import Session

from functools import lru_cache
from bot_api_v1.app.core.config import Settings

def get_db() -> Session:
    # 临时返回 None，作为数据库会话的占位符
    # 后续集成数据库时再替换为真实的会话
    return None


@lru_cache()
def get_settings():
    """
    Creates a cached instance of the settings.
    This avoids loading the settings multiple times.
    """
    return Settings()
