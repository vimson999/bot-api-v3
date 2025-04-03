"""
商品服务模块

提供商品查询、管理等功能
"""
from asyncio import gather
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot_api_v1.app.core.logger import logger
from bot_api_v1.app.models.meta_product import MetaProduct
from bot_api_v1.app.utils.decorators.log_service_call import log_service_call
from bot_api_v1.app.utils.decorators.gate_keeper import gate_keeper

class ProductService:
    """商品服务类"""
    
    @gate_keeper()
    @log_service_call()
    async def get_product_list(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        获取商品列表
        
        Args:
            db: 数据库会话
            
        Returns:
            List[Dict[str, Any]]: 商品列表数据
        """
        try:
            # 查询活跃状态的商品
            stmt = select(
                MetaProduct.id,
                MetaProduct.name,
                MetaProduct.cover_image,
                MetaProduct.original_price,
                MetaProduct.sale_price,
                MetaProduct.description,
                MetaProduct.point_amount,
                MetaProduct.inventory_count,
                MetaProduct.tags
            ).where(
                MetaProduct.status == 1
            ).order_by(MetaProduct.sort)
            
            result = await db.execute(stmt)
            products = result.all()
            
            # 转换为字典列表
            product_list = []
            for product in products:
                product_dict = {
                    "id": product.id,
                    "name": product.name,
                    "cover_image": product.cover_image,
                    "original_price": float(product.original_price) if product.original_price else 0,
                    "sale_price": float(product.sale_price) if product.sale_price else 0,
                    "description": product.description,
                    "point_amount": product.point_amount,
                    'tags': product.tags,
                    "stock": product.inventory_count
                }
                product_list.append(product_dict)
            
            return product_list
        except Exception as e:
            logger.error(f"获取商品列表失败: {str(e)}", exc_info=True)
            # 返回空列表而不是抛出异常，避免整个请求失败
            return []