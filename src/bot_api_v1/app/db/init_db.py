# bot_api_v1/app/db/init_db.py

import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from sqlalchemy.schema import CreateSchema
from bot_api_v1.app.db.base import Base
from bot_api_v1.app.db.session import engine, get_db
from bot_api_v1.app.core.config import settings
from alembic.config import Config
from alembic import command
import os
from pathlib import Path

logger = logging.getLogger(__name__)

async def check_connection():
    """验证数据库连接"""
    try:
        from bot_api_v1.app.db.session import check_db_connection
        return await check_db_connection()
    except Exception as e:
        logger.error(f"Database connection check failed: {str(e)}")
        return False

async def create_extensions():
    """创建必要的PostgreSQL扩展"""
    extensions = ["uuid-ossp", "pg_stat_statements"]
    try:
        async with engine.begin() as conn:
            for ext in extensions:
                await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS \"{ext}\""))
        logger.info(f"Database extensions created: {', '.join(extensions)}")
    except Exception as e:
        logger.error(f"Failed to create database extensions: {str(e)}")
        raise

async def init_db(use_alembic=True):
    """
    初始化数据库结构 
    
    Args:
        use_alembic: 是否使用Alembic进行迁移，生产环境应为True
    """
    try:
        # 检查连接
        connection_ok = await check_connection()
        if not connection_ok:
            raise Exception("无法连接到数据库，初始化中止")
        
        # 创建扩展
        await create_extensions()
        
        # 在生产环境中，应该使用Alembic来管理表结构
        if use_alembic and settings.ENVIRONMENT != "development":
            logger.info("使用Alembic迁移创建/更新数据库结构")
            # 获取项目根目录
            project_root = Path(__file__).parent.parent.parent.parent
            alembic_cfg = Config(project_root / "alembic.ini")
            command.upgrade(alembic_cfg, "head")
            return
        
        # 开发环境可以直接使用SQLAlchemy创建表
        async with engine.begin() as conn:
            # 在开发环境中可以选择重新创建所有表
            # if settings.ENVIRONMENT == "development" and settings.DB_DROP_AND_CREATE_ALL:
            #     logger.warning("删除所有现有表! 仅用于开发环境!")
            #     await conn.run_sync(Base.metadata.drop_all)
            
            # 确保schema存在
            if settings.DB_SCHEMA and settings.DB_SCHEMA != "public":
                try:
                    await conn.execute(CreateSchema(settings.DB_SCHEMA, if_not_exists=True))
                except Exception as e:
                    logger.error(f"创建schema失败: {str(e)}")
                    
            # 创建表
            await conn.run_sync(Base.metadata.create_all)
            
        logger.info("数据库表初始化成功")
    except Exception as e:
        logger.error(f"初始化数据库出错: {str(e)}")
        raise

async def wait_for_db(max_retries: int = 60, interval: int = 1):
    """等待数据库可用"""
    retry_count = 0
    while retry_count < max_retries:
        connection_ok = await check_connection()
        if connection_ok:
            logger.info("Database is available")
            return True
        
        retry_count += 1
        logger.warning(f"Database not available, retrying in {interval}s... ({retry_count}/{max_retries})")
        await asyncio.sleep(interval)
    
    logger.error(f"Database connection failed after {max_retries} attempts")
    return False