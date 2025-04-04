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
    
    # 数据库配置调整
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://cappa_rw:RWcappaDb!!!2025@101.35.56.140:5432/cappadocia_v1"
    )
    # 减少默认连接池大小，避免创建过多连接
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    # 减少默认最大溢出连接数
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    # 减少连接回收时间，使连接更快被释放
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "900"))  # 减少到15分钟
    # 减少连接超时时间
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "10"))  # 减少到10秒
    # 添加空闲事务超时设置
    DB_IDLE_TRANSACTION_TIMEOUT: int = int(os.getenv("DB_IDLE_TRANSACTION_TIMEOUT", "300"))  # 5分钟
    # 启用会话追踪，便于调试连接问题
    DB_TRACE_SESSIONS: bool = os.getenv("DB_TRACE_SESSIONS", "true").lower() == "true"
    # 添加连接池使用率阈值配置
    DB_POOL_USAGE_WARNING_THRESHOLD: float = float(os.getenv("DB_POOL_USAGE_WARNING_THRESHOLD", "0.7"))  # 当使用率超过70%时发出警告
    # 添加连接获取重试配置
    DB_CONNECTION_RETRY_ATTEMPTS: int = int(os.getenv("DB_CONNECTION_RETRY_ATTEMPTS", "3"))  # 连接获取重试次数
    DB_CONNECTION_RETRY_DELAY: float = float(os.getenv("DB_CONNECTION_RETRY_DELAY", "0.5"))  # 重试延迟(秒)
    # 添加连接统计间隔
    DB_CONNECTION_STATS_INTERVAL: int = int(os.getenv("DB_CONNECTION_STATS_INTERVAL", "300"))  # 5分钟记录一次连接统计
    # 添加预处理语句缓存大小
    DB_PREPARED_STATEMENT_CACHE_SIZE: int = int(os.getenv("DB_PREPARED_STATEMENT_CACHE_SIZE", "100"))  # 预处理语句缓存大小
    # 连接参数
    DB_CONNECT_ARGS: Dict[str, Any] = {
        "server_settings": {
            "application_name": f"{os.getenv('PROJECT_NAME', 'API服务')}-{os.getenv('ENVIRONMENT', 'development')}",
            "statement_timeout": os.getenv("DB_STATEMENT_TIMEOUT", "30000"),  # 30秒
            "lock_timeout": os.getenv("DB_LOCK_TIMEOUT", "5000"),  # 5秒
            "idle_in_transaction_session_timeout": os.getenv("DB_IDLE_TRANSACTION_TIMEOUT", "300000"),  # 5分钟
            # 可选的预处理语句缓存大小
            "prepared_statement_cache_size": os.getenv("DB_PREPARED_STATEMENT_CACHE_SIZE", "100"),
        }
    }
    
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"
    DB_ECHO_POOL: bool = os.getenv("DB_ECHO_POOL", "false").lower() == "true"
    DB_SCHEMA: str = os.getenv("DB_SCHEMA", "public") 
    DB_STATEMENT_TIMEOUT: int = int(os.getenv("DB_STATEMENT_TIMEOUT", "30000"))  # 30秒
    DB_LOCK_TIMEOUT: int = int(os.getenv("DB_LOCK_TIMEOUT", "5000"))  # 5秒
    DB_SLOW_QUERY_LOG: float = float(os.getenv("DB_SLOW_QUERY_LOG", "1.0"))  # 1秒以上查询记录
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


    # Feishu 捷径插件配置
    ALLOWED_FEISHU_PACK_IDS: List[str] = os.getenv(
        "ALLOWED_FEISHU_PACK_IDS", 
        "debug_pack_id_1742102777762"
    ).split(",")


    WECHAT_MP_TOKEN: str = os.getenv("WECHAT_MP_TOKEN", "vims32keyLilymvpabc12")  
    WECHAT_MP_APPID: str = os.getenv("WECHAT_MP_APPID", "wxd5b92e8f6f424d09")
    WECHAT_MP_SECRET: str = os.getenv("WECHAT_MP_SECRET", "dd7f200be2e3ddce83a5dffb069b9fa5")

    CURRENT_WECHAT_MP_MENU_VERSION: int = int(os.getenv("CURRENT_WECHAT_MP_MENU_VERSION", "0"))
    TARGET_WECHAT_MP_MENU_VERSION: int = int(os.getenv("TARGET_WECHAT_MP_MENU_VERSION", "1"))

    WECHAT_MINI_APPID: str = os.getenv("WECHAT_MINI_APPID", "")
    WECHAT_MINI_SECRET: str = os.getenv("WECHAT_MINI_SECRET", "")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_DAYS: int = int(os.getenv("JWT_EXPIRATION_DAYS", "7"))
    WECHAT_MERCHANT_KEY: str = os.getenv("WECHAT_MERCHANT_KEY", "")

    DOMAIN_API_URL : str = os.getenv("DOMAIN_API_URL", "http://iw6i1vjj93ml.guyubao.com")
    H5_FRONTEND_URL: str = os.getenv("H5_FRONTEND_URL", "http://iw6i1vjj93ml.guyubao.com/h5")  # 前端H5页面地址

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
                # 减少生产环境连接池大小，避免超出PostgreSQL最大连接数
                "DB_POOL_SIZE": 5,
                "DB_MAX_OVERFLOW": 10,
                "DEBUG": False,
            },
        }
        return all_envs.get(self.ENVIRONMENT, {}).get(key, getattr(self, key))


@lru_cache()
def get_settings() -> Settings:
    """缓存的设置获取函数"""
    return Settings()

settings = get_settings()