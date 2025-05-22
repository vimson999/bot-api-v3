# src/bot_api_v1/app/core/config.py (已更新)

from re import S
from pydantic_settings import BaseSettings
import os
from typing import Optional, List, Dict, Any, Union
import json
from functools import lru_cache
import secrets
from pathlib import Path


class Settings(BaseSettings):
    # 基本应用配置
    PROJECT_NAME: str = "bot_api_v1"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    DEBUG: bool = False
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))

    SITE_JS_SECRET_KEY: str = os.getenv("SITE_JS_SECRET_KEY", secrets.token_urlsafe(32))
    
    # 日期时间和地区设置
    TIMEZONE: str = "Asia/Shanghai" # 将被 Celery 使用
    DEFAULT_LOCALE: str = "zh_CN"
    
    # 数据库配置调整 (保持不变)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://cappa_rw:RWcappaDb!!!2025@101.35.56.140:5432/cappadocia_v1"
    )
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "900"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "120"))
    DB_IDLE_TRANSACTION_TIMEOUT: int = int(os.getenv("DB_IDLE_TRANSACTION_TIMEOUT", "300"))
    DB_TRACE_SESSIONS: bool = os.getenv("DB_TRACE_SESSIONS", "true").lower() == "true"
    DB_POOL_USAGE_WARNING_THRESHOLD: float = float(os.getenv("DB_POOL_USAGE_WARNING_THRESHOLD", "0.7"))
    DB_CONNECTION_RETRY_ATTEMPTS: int = int(os.getenv("DB_CONNECTION_RETRY_ATTEMPTS", "3"))
    DB_CONNECTION_RETRY_DELAY: float = float(os.getenv("DB_CONNECTION_RETRY_DELAY", "0.5"))
    DB_CONNECTION_STATS_INTERVAL: int = int(os.getenv("DB_CONNECTION_STATS_INTERVAL", "300"))
    DB_PREPARED_STATEMENT_CACHE_SIZE: int = int(os.getenv("DB_PREPARED_STATEMENT_CACHE_SIZE", "100"))
    DB_CONNECT_ARGS: Dict[str, Any] = {
        "server_settings": {
            "application_name": f"{os.getenv('PROJECT_NAME', 'API服务')}-{os.getenv('ENVIRONMENT', 'development')}",
            "statement_timeout": os.getenv("DB_STATEMENT_TIMEOUT", "30000"),
            "lock_timeout": os.getenv("DB_LOCK_TIMEOUT", "5000"),
            "idle_in_transaction_session_timeout": os.getenv("DB_IDLE_TRANSACTION_TIMEOUT", "300000"),
            "prepared_statement_cache_size": os.getenv("DB_PREPARED_STATEMENT_CACHE_SIZE", "100"),
        }
    }
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"
    DB_ECHO_POOL: bool = os.getenv("DB_ECHO_POOL", "false").lower() == "true"
    DB_SCHEMA: str = os.getenv("DB_SCHEMA", "public") 
    DB_STATEMENT_TIMEOUT: int = int(os.getenv("DB_STATEMENT_TIMEOUT", "30000"))
    DB_LOCK_TIMEOUT: int = int(os.getenv("DB_LOCK_TIMEOUT", "5000"))
    DB_SLOW_QUERY_LOG: float = float(os.getenv("DB_SLOW_QUERY_LOG", "1.0"))
    DB_CONNECT_RETRIES: int = int(os.getenv("DB_CONNECT_RETRIES", "5"))
    DB_CONNECT_RETRY_INTERVAL: int = int(os.getenv("DB_CONNECT_RETRY_INTERVAL", "5"))
    DB_DROP_AND_CREATE_ALL: bool = os.getenv("DB_DROP_AND_CREATE_ALL", "false").lower() == "true"
    CREATE_TEST_DATA: bool = os.getenv("CREATE_TEST_DATA", "false").lower() == "true"
    

    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
    SHARED_TEMP_DIR : str = os.getenv("SHARED_TEMP_DIR", "/Users/v9/Downloads/nfs")
    SHARED_MNT_DIR : str = os.getenv("SHARED_MNT_DIR", "/Users/v9/Downloads/nfs")


    # 缓存设置
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL") # 这个可用于通用 Redis 缓存
    CACHE_EXPIRATION: int = int(os.getenv("CACHE_EXPIRATION", "100"))
    CACHE_REDIS_URL: str = os.getenv(
        "CACHE_REDIS_URL",
        # "redis://:login4RDS!!!@101.35.56.140:6379/2" # !! 默认值指向远程 Redis DB 2 !!
        "redis://localhost:6379/2"
    )



    # --- 新增 Celery 配置 ---
    CELERY_BROKER_URL: str = os.getenv(
        "CELERY_BROKER_URL", 
        # "redis://:login4RDS!!!@101.35.56.140:6379/0" 
        "redis://:login4RDS!!!@10.0.16.12:6379/0" 
    )
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND", 
        # "redis://:login4RDS!!!@101.35.56.140:6379/1" 
        "redis://:login4RDS!!!@10.0.16.12:6379/1" 
    )
    CELERY_TASK_SERIALIZER: str = os.getenv("CELERY_TASK_SERIALIZER", "json")
    CELERY_RESULT_SERIALIZER: str = os.getenv("CELERY_RESULT_SERIALIZER", "json")
    _celery_accept_content_str: str = os.getenv("CELERY_ACCEPT_CONTENT", '["json"]') 
    CELERY_ACCEPT_CONTENT: List[str] = json.loads(_celery_accept_content_str)
    CELERY_ENABLE_UTC: bool = os.getenv("CELERY_ENABLE_UTC", "true").lower() == "true"
    CELERY_RESULT_EXPIRES: int = int(os.getenv("CELERY_RESULT_EXPIRES", "3600")) 
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP: bool = os.getenv("CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP", "true").lower() == "true"
    # --- 结束新增 Celery 配置 ---

    # 安全设置 (保持不变)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    ALGORITHM: str = "HS256"
    CORS_ORIGINS: List[str] = json.loads(os.getenv("CORS_ORIGINS", '["*"]'))
    ALLOWED_HOSTS: List[str] = json.loads(os.getenv("ALLOWED_HOSTS", '["*"]'))
    
    # 日志配置 (保持不变)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json")
    ENABLE_DB_LOGGING: bool = os.getenv("ENABLE_DB_LOGGING", "false").lower() == "true"
    LOG_TO_STDOUT: bool = os.getenv("LOG_TO_STDOUT", "true").lower() == "true"
    LOG_TO_FILE: bool = os.getenv("LOG_TO_FILE", "true").lower() == "true"
    LOG_FILE_PATH: Optional[str] = os.getenv("LOG_FILE_PATH", "/Users/v9/Downloads/nfs/logs")


    # 性能和限流设置 (保持不变)
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "100"))
    WORKERS_COUNT: int = int(os.getenv("WORKERS_COUNT", "4"))

    # Feishu 捷径插件配置 (保持不变)
    ALLOWED_FEISHU_PACK_IDS: List[str] = os.getenv(
        "ALLOWED_FEISHU_PACK_IDS", 
        "debug_pack_id_1742102777762"
    ).split(",")

    # 微信相关配置 (保持不变)
    # WECHAT_MP_TOKEN: str = os.getenv("WECHAT_MP_TOKEN", "vims32keyLilymvpabc12")  
    # WECHAT_MP_APPID: str = os.getenv("WECHAT_MP_APPID", "wxd5b92e8f6f424d09")
    # WECHAT_MP_SECRET: str = os.getenv("WECHAT_MP_SECRET", "dd7f200be2e3ddce83a5dffb069b9fa5")

    WECHAT_MP_TOKEN: str = os.getenv("WECHAT_MP_TOKEN", "vims32keyLilymvpabc12")  
    WECHAT_MP_APPID: str = os.getenv("WECHAT_MP_APPID", "wxa690d4c27e35c4a2")
    WECHAT_MP_SECRET: str = os.getenv("WECHAT_MP_SECRET", "cf9b6d593bf43a609261e858548f2588")
    WECHAT_MP_ENCODINGAESKEY: str = os.getenv("WECHAT_MP_ENCODINGAESKEY", "vnCp3XQ8nE7Iw5n4kDieXzuGxoFFgWa5o1mbEM97Dbv")
    WECHAT_MERCHANT_ID: str = os.getenv("WECHAT_MERCHANT_ID","1716724012")


    CURRENT_WECHAT_MP_MENU_VERSION: int = int(os.getenv("CURRENT_WECHAT_MP_MENU_VERSION", "0"))
    TARGET_WECHAT_MP_MENU_VERSION: int = int(os.getenv("TARGET_WECHAT_MP_MENU_VERSION", "1"))
    WECHAT_MINI_APPID: str = os.getenv("WECHAT_MINI_APPID", "")
    WECHAT_MINI_SECRET: str = os.getenv("WECHAT_MINI_SECRET", "")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_DAYS: int = int(os.getenv("JWT_EXPIRATION_DAYS", "7"))

    WECHAT_MERCHANT_KEY: str = os.getenv("WECHAT_MERCHANT_KEY", "7wPzL9qS2mN5hG1dF8cVbJ0rX3kA6tYe")
    WECHAT_MERCHANT_APIV2: str = os.getenv("WECHAT_MERCHANT_APIV2", "7wPzL9qS2mN5hG1dF8cVbJ0rX3kA6tYe")
    WECHAT_MERCHANT_APIV3: str = os.getenv("WECHAT_MERCHANT_APIV3", "Zq5K9xP1mJ0rD7vS3cT8wA2hL6gN4fYb")
    WECHAT_MERCHANT_PUBKEY: str = os.getenv("WECHAT_MERCHANT_PUBKEY", "PUB_KEY_ID_0117167240122025051300451926000601")

    # URL 配置 (保持不变)
    DOMAIN_API_URL : str = os.getenv("DOMAIN_API_URL", "http://iw6i1vjj93ml.guyubao.com")
    H5_FRONTEND_URL: str = os.getenv("H5_FRONTEND_URL", "http://iw6i1vjj93ml.guyubao.com/h5")
    DEV_URL : str = os.getenv("DEV_URL", "http://127.0.0.1:8083")


    DOMAIN_MAIN_URL : str = os.getenv("DOMAIN_MAIN_URL", "https://www.xiaoshanqing.tech")
    DOMAIN_IP_URL : str = os.getenv("DOMAIN_IP_URL", "http://42.192.40.44")
    KUAISHOU_SITE : str = os.getenv("KUAISHOU_SITE", "http://127.0.0.1:9000")
    TIKTOK_COOKIE_FILE : str = os.getenv("TIKTOK_COOKIE_FILE","/Users/v9/Documents/workspace/v9/code/bot-api-v1/src/bot_api_v1/app/config/cookies/tk.txt")

    OPEN_ROUTER_API_KEY_QW : str = os.getenv("OPEN_ROUTER_API_KEY_QW","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")
    OPEN_ROUTER_API_MODEL_QW : str = os.getenv("OPEN_ROUTER_API_MODEL_QW","deepseek/deepseek-prover-v2:free")
    OPEN_ROUTER_API_URL : str = os.getenv("OPEN_ROUTER_API_URL","https://openrouter.ai/api/v1")

    BASIC_CONSUME_POINT : int = int(os.getenv("BASIC_CONSUME_POINT", "5"))

    # 其他配置 (保持不变)

    class Config:
        env_file = ".env" # 会自动加载 .env 文件中的环境变量
        env_file_encoding = "utf-8"
        case_sensitive = True # 环境变量区分大小写
        
        @classmethod
        def customise_sources(
            cls,
            init_settings,
            env_settings,
            file_secret_settings,
        ):
            return (
                init_settings,
                env_settings, # 环境变量优先级高
                file_secret_settings,
            )
    
    def get_environment_specific(self, key: str) -> Dict[str, Any]:
        # ... (保持不变) ...
        all_envs = {
            "development": { "DB_POOL_SIZE": 2, "DB_MAX_OVERFLOW": 5, "DEBUG": True, },
            "testing": { "DB_POOL_SIZE": 2, "DB_MAX_OVERFLOW": 5, "DEBUG": True, },
            "production": { "DB_POOL_SIZE": 5, "DB_MAX_OVERFLOW": 10, "DEBUG": False, },
        }
        return all_envs.get(self.ENVIRONMENT, {}).get(key, getattr(self, key))


@lru_cache()
def get_settings() -> Settings:
    """缓存的设置获取函数"""
    # Pydantic-settings 会在实例化时自动加载 .env 文件和环境变量
    return Settings()

settings = get_settings() # 创建全局 settings 实例


# # --- !! 添加以下打印语句用于调试 !! ---
# print("--- [DEBUG] Settings Object Initialized ---")
# print(f"ENVIRONMENT: {getattr(settings, 'ENVIRONMENT', 'N/A')}") # 使用 getattr 防御
# print(f"CELERY_BROKER_URL: {getattr(settings, 'CELERY_BROKER_URL', 'N/A')}")
# print(f"CELERY_RESULT_BACKEND: {getattr(settings, 'CELERY_RESULT_BACKEND', 'N/A')}")
# print(f"CACHE_REDIS_URL: {getattr(settings, 'CACHE_REDIS_URL', 'N/A')}") # 重点观察这个！
# print("--- [DEBUG] End Settings Init Check ---")
# # --- !! 结束添加打印语句 !! ---