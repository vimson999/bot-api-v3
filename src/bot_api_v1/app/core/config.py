# bot_api_v1/app/core/config.py

from pydantic_settings import BaseSettings
import os
from typing import Optional, List, Dict, Any, Union
import json
from functools import lru_cache
import secrets
from pathlib import Path


class Settings(BaseSettings):
    # 基本应用配置
    PROJECT_NAME: str = "API服务"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    DEBUG: bool = False
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    
    # 日期时间和地区设置
    TIMEZONE: str = "Asia/Shanghai"
    DEFAULT_LOCALE: str = "zh_CN"
    
    # 数据库配置
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://cappa_rw:RWcappaDb!!!2025@101.35.56.140:5432/cappadocia_v1"
    )
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"
    DB_ECHO_POOL: bool = os.getenv("DB_ECHO_POOL", "false").lower() == "true"
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    DB_SCHEMA: str = os.getenv("DB_SCHEMA", "public") 
    DB_STATEMENT_TIMEOUT: int = int(os.getenv("DB_STATEMENT_TIMEOUT", "30000"))  # 30秒
    DB_LOCK_TIMEOUT: int = int(os.getenv("DB_LOCK_TIMEOUT", "5000"))  # 5秒
    DB_SLOW_QUERY_LOG: float = float(os.getenv("DB_SLOW_QUERY_LOG", "1.0"))  # 1秒以上查询记录
    DB_TRACE_SESSIONS: bool = os.getenv("DB_TRACE_SESSIONS", "false").lower() == "true"
    DB_CONNECT_RETRIES: int = int(os.getenv("DB_CONNECT_RETRIES", "5"))
    DB_CONNECT_RETRY_INTERVAL: int = int(os.getenv("DB_CONNECT_RETRY_INTERVAL", "5"))
    
    # 开发设置
    DB_DROP_AND_CREATE_ALL: bool = os.getenv("DB_DROP_AND_CREATE_ALL", "false").lower() == "true"
    CREATE_TEST_DATA: bool = os.getenv("CREATE_TEST_DATA", "false").lower() == "true"
    
    # 缓存设置
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    CACHE_EXPIRATION: int = int(os.getenv("CACHE_EXPIRATION", "3600"))  # 1小时
    
    # 安全设置
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    ALGORITHM: str = "HS256"
    CORS_ORIGINS: List[str] = json.loads(os.getenv("CORS_ORIGINS", '["*"]'))
    ALLOWED_HOSTS: List[str] = json.loads(os.getenv("ALLOWED_HOSTS", '["*"]'))
    
    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json")  # plain或json
    ENABLE_DB_LOGGING: bool = os.getenv("ENABLE_DB_LOGGING", "false").lower() == "true"
    LOG_TO_STDOUT: bool = os.getenv("LOG_TO_STDOUT", "true").lower() == "true"
    LOG_TO_FILE: bool = os.getenv("LOG_TO_FILE", "true").lower() == "true"
    LOG_FILE_PATH: Optional[str] = os.getenv("LOG_FILE_PATH")

    
    # 性能和限流设置
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "100"))
    WORKERS_COUNT: int = int(os.getenv("WORKERS_COUNT", "4"))
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        
        @classmethod
        def customise_sources(
            cls,
            init_settings,
            env_settings,
            file_secret_settings,
        ):
            return (
                init_settings,
                env_settings,
                file_secret_settings,
            )
    
    def get_environment_specific(self, key: str) -> Dict[str, Any]:
        """获取特定环境的配置"""
        all_envs = {
            "development": {
                "DB_POOL_SIZE": 2,
                "DB_MAX_OVERFLOW": 5,
                "DEBUG": True,
            },
            "testing": {
                "DB_POOL_SIZE": 2,
                "DB_MAX_OVERFLOW": 5,
                "DEBUG": True,
            },
            "production": {
                "DB_POOL_SIZE": 10,
                "DB_MAX_OVERFLOW": 20,
                "DEBUG": False,
            },
        }
        return all_envs.get(self.ENVIRONMENT, {}).get(key, getattr(self, key))

@lru_cache()
def get_settings() -> Settings:
    """缓存的设置获取函数"""
    return Settings()

settings = get_settings()
