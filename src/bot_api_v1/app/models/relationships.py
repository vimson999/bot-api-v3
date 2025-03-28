"""
模型关系定义模块

在所有模型都定义完成后设置它们之间的关系，避免循环引用问题。
"""
from sqlalchemy.orm import relationship, registry, configure_mappers

from bot_api_v1.app.models.meta_order import MetaOrder
from bot_api_v1.app.models.meta_user import MetaUser
from bot_api_v1.app.models.meta_product import MetaProduct
from bot_api_v1.app.models.rel_product_package import RelProductPackage
from bot_api_v1.app.models.meta_promotion import MetaPromotion
from bot_api_v1.app.models.log_payment_callback import LogPaymentCallback
from bot_api_v1.app.models.rel_points_transaction import RelPointsTransaction

# 创建关系
def setup_relationships():
    # 设置MetaOrder的关系
    MetaOrder.user = relationship("MetaUser", back_populates="orders")
    MetaOrder.product = relationship("MetaProduct", back_populates="orders")
    MetaOrder.package = relationship("RelProductPackage", back_populates="orders")
    MetaOrder.promotion = relationship("MetaPromotion", back_populates="orders")
    MetaOrder.payment_callbacks = relationship("LogPaymentCallback", back_populates="order")
    MetaOrder.points_transactions = relationship("RelPointsTransaction", back_populates="order")
    
    # 设置其他模型的关系
    MetaUser.orders = relationship("MetaOrder", back_populates="user")
    MetaProduct.orders = relationship("MetaOrder", back_populates="product")
    RelProductPackage.orders = relationship("MetaOrder", back_populates="package")
    MetaPromotion.orders = relationship("MetaOrder", back_populates="promotion")
    LogPaymentCallback.order = relationship("MetaOrder", back_populates="payment_callbacks")
    RelPointsTransaction.order = relationship("MetaOrder", back_populates="points_transactions")
    
    # 确保配置生效
    configure_mappers()

# 执行设置
setup_relationships()