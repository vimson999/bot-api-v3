# src/bot_api_v1/app/core/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "Production API"
    db_url: Optional[str] = None  # 设为可选，默认为None
    cache_url: Optional[str] = None  # 设为可选，默认为None
    log_level: str = "INFO"
    page_size: int = 20
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
