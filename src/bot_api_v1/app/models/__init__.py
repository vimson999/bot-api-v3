# 首先导入基类
from bot_api_v1.app.models.base import Base

# 导入所有模型 - 确保顺序合理
from .log_trace import LogTrace
from .meta_user import MetaUser
from .meta_app import MetaApp
from .meta_group import MetaGroup
from .meta_path import MetaPath
from .meta_access_policy import MetaAccessPolicy
from .relations import RelPolicyBinding, RelUserGroup
from .meta_product import MetaProduct  
from .meta_promotion import MetaPromotion
from .rel_product_package import RelProductPackage
from .meta_order import MetaOrder
from .log_payment_callback import LogPaymentCallback
from .rel_points_transaction import RelPointsTransaction
from .meta_user_points import MetaUserPoints
from .meta_auth_key import MetaAuthKey

# 最后才导入关系设置 - 这非常重要
from .relationships import setup_relationships

# 导出所有模型
__all__ = [
    "Base",
    "LogTrace",
    "MetaUser",
    "MetaApp",
    "MetaGroup",
    "MetaPath",
    "MetaAccessPolicy", 
    "RelPolicyBinding",
    "RelUserGroup",
    "MetaProduct",
    "MetaPromotion",
    "RelProductPackage",
    "MetaOrder",
    "LogPaymentCallback", 
    "RelPointsTransaction",
    "MetaUserPoints",
    "MetaAuthKey"
]