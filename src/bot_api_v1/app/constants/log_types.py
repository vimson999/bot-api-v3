# src/bot_api_v1/app/constants/log_types.py

from enum import Enum

class LogEventType(str, Enum):
    """日志事件类型枚举"""
    # 用户相关
    USER_REGISTER = "user_register"
    USER_LOGIN = "user_login"
    USER_REGISTER_LOGIN = "user_register_login"  # 微信小程序新用户
    USER_LOGOUT = "user_logout"
    USER_INFO_UPDATE = "user_info_update"
    USER_TOKEN_REFRESH = "user_token_refresh"
    USER_TOKEN_INVALID = "user_token_invalid"
    
    # 微信相关
    WECHAT_AUTH = "wechat_auth"
    WECHAT_DECRYPT_ERROR = "wechat_decrypt_error"
    WECHAT_API_ERROR = "wechat_api_error"
    WECHAT_CODE_EXCHANGE = "wechat_code_exchange"
    
    # 一般请求
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    
    # 系统事件
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SYSTEM_ERROR = "system_error"
    
    # 数据操作
    DATA_CREATE = "data_create"
    DATA_UPDATE = "data_update"
    DATA_DELETE = "data_delete"
    DATA_QUERY = "data_query"


class LogSource(str, Enum):
    """日志来源枚举"""
    API = "api"
    WECHAT = "wechat"
    WECHAT_MINI = "wechat_mini"  # 专门区分微信小程序
    WEB = "web"
    MOBILE = "mobile"
    SYSTEM = "system"
    TASK = "task"
    SCRIPT = "script"
    BACKGROUND = "background"
    SCHEDULER = "scheduler"