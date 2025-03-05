# src/bot_api_v1/app/core/config.py
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    app_name: str = "Production API"
    db_url: Optional[str] = None  # 设为可选，默认为None
    cache_url: Optional[str] = None  # 设为可选，默认为None
    log_level: str = "INFO"
    page_size: int = 20

    
    # 数据库配置 - PostgreSQL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://cappa_rw:RWcappaDb!!!2025@101.35.56.140:5432/cappadocia_v1"
    )
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
