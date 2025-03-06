# bot_api_v1/app/services/base.py

from typing import Generic, TypeVar, Type, Any, Dict, List, Optional, Union, Callable
from sqlalchemy import select, update, delete, and_, or_, desc, asc, func, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.exc import SQLAlchemyError
import logging
from fastapi.encoders import jsonable_encoder
from bot_api_v1.app.db.base import Base
from datetime import datetime
import uuid
from pydantic import BaseModel

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

logger = logging.getLogger(__name__)

class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model
        self._soft_delete = hasattr(model, 'status')
    
    async def get(
        self, 
        db: AsyncSession, 
        id: Union[uuid.UUID, str, int],
        include_deleted: bool = False
    ) -> Optional[ModelType]:
        """通过ID获取单条记录"""
        try:
            filters = [self.model.id == id]
            if not include_deleted and self._soft_delete:
                filters.append(self.model.status != 0)
                
            stmt = select(self.model).where(and_(*filters))
            result = await db.execute(stmt)
            return result.scalars().first()
        except SQLAlchemyError as e:
            logger.error(f"Error getting {self.model.__name__} by id: {str(e)}")
            raise
    
    async def exists(self, db: AsyncSession, id: Any) -> bool:
        """检查记录是否存在"""
        try:
            stmt = select(exists().where(self.model.id == id))
            result = await db.execute(stmt)
            return result.scalar()
        except SQLAlchemyError as e:
            logger.error(f"Error checking existence for {self.model.__name__}: {str(e)}")
            raise
    
    async def get_multi(
        self, 
        db: AsyncSession, 
        *,
        skip: int = 0, 
        limit: int = 100,
        filters: List[Any] = None,
        order_by: List[Any] = None,
        include_deleted: bool = False
    ) -> List[ModelType]:
        """获取多条记录，支持过滤和排序"""
        try:
            all_filters = filters or []
            if not include_deleted and self._soft_delete:
                all_filters.append(self.model.status != 0)
                
            stmt = select(self.model)
            
            if all_filters:
                stmt = stmt.where(and_(*all_filters))
                
            if order_by:
                stmt = stmt.order_by(*order_by)
            elif hasattr(self.model, 'sort'):
                stmt = stmt.order_by(asc(self.model.sort), desc(self.model.created_at))
            else:
                stmt = stmt.order_by(desc(self.model.created_at))
                
            stmt = stmt.offset(skip).limit(limit)
            
            result = await db.execute(stmt)
            return result.scalars().fetchall()
        except SQLAlchemyError as e:
            logger.error(f"Error getting multiple {self.model.__name__}: {str(e)}")
            raise
    
    async def count(
        self, 
        db: AsyncSession, 
        filters: List[Any] = None,
        include_deleted: bool = False
    ) -> int:
        """计算记录总数"""
        try:
            all_filters = filters or []
            if not include_deleted and self._soft_delete:
                all_filters.append(self.model.status != 0)
                
            stmt = select(func.count()).select_from(self.model)
            
            if all_filters:
                stmt = stmt.where(and_(*all_filters))
                
            result = await db.execute(stmt)
            return result.scalar()
        except SQLAlchemyError as e:
            logger.error(f"Error counting {self.model.__name__}: {str(e)}")
            raise
    
    async def create(self, db: AsyncSession, *, obj_in: Union[CreateSchemaType, Dict[str, Any]]) -> ModelType:
        """创建新记录"""
        try:
            obj_in_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)
            db_obj = self.model(**obj_in_data)
            db.add(db_obj)
            await db.commit()
            await db.refresh(db_obj)
            return db_obj
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"Error creating {self.model.__name__}: {str(e)}")
            raise
    
    async def update(
        self, 
        db: AsyncSession, 
        *, 
        obj_current: ModelType,
        obj_in: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> Optional[ModelType]:
        """更新现有记录"""
        try:
            obj_data = jsonable_encoder(obj_current)
            update_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)
            
            # 过滤掉值为None的字段，除非明确设置了None
            if isinstance(obj_in, dict):
                update_data = {k: v for k, v in update_data.items() if v is not None}
            
            for field in obj_data:
                if field in update_data:
                    setattr(obj_current, field, update_data[field])
            
            if hasattr(obj_current, 'updated_at'):
                obj_current.updated_at = datetime.now()
                
            db.add(obj_current)
            await db.commit()
            await db.refresh(obj_current)
            return obj_current
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"Error updating {self.model.__name__}: {str(e)}")
            raise
    
    async def delete(
        self, 
        db: AsyncSession, 
        *, 
        id: Any,
        hard_delete: bool = False
    ) -> Optional[ModelType]:
        """删除记录，支持软删除和硬删除"""
        try:
            # 软删除
            if self._soft_delete and not hard_delete:
                stmt = (
                    update(self.model)
                    .where(self.model.id == id)
                    .values(status=0, updated_at=datetime.now())
                    .returning(self.model)
                )
                result = await db.execute(stmt)
                await db.commit()
                return result.scalars().first()
            
            # 硬删除
            else:
                stmt = (
                    delete(self.model)
                    .where(self.model.id == id)
                    .returning(self.model)
                )
                result = await db.execute(stmt)
                await db.commit()
                return result.scalars().first()
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"Error deleting {self.model.__name__}: {str(e)}")
            raise
    
    async def bulk_create(
        self, 
        db: AsyncSession, 
        *, 
        objs_in: List[Union[CreateSchemaType, Dict[str, Any]]]
    ) -> List[ModelType]:
        """批量创建记录"""
        try:
            db_objs = []
            for obj_in in objs_in:
                obj_in_data = obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)
                db_obj = self.model(**obj_in_data)
                db.add(db_obj)
                db_objs.append(db_obj)
                
            await db.commit()
            
            # 重新加载所有对象
            for db_obj in db_objs:
                await db.refresh(db_obj)
                
            return db_objs
        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"Error bulk creating {self.model.__name__}: {str(e)}")
            raise
