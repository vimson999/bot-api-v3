import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url
import contextlib
import logging
from bot_api_v1.app.core.config import settings
import time
import asyncio

from bot_api_v1.app.db.metrics import patch_sqlalchemy_metrics


logger = logging.getLogger(__name__)

# 添加连接重试逻辑
def get_engine(url, **kwargs):
    """创建带有重试逻辑的数据库引擎"""
    max_retries = settings.DB_CONNECT_RETRIES
    retry_interval = settings.DB_CONNECT_RETRY_INTERVAL
    
    for i in range(max_retries):
        try:
            return create_async_engine(url, **kwargs)
        except Exception as e:
            if i < max_retries - 1:
                logger.warning(f"Database connection attempt {i+1} failed: {str(e)}. Retrying in {retry_interval}s...")
                time.sleep(retry_interval)
            else:
                logger.error(f"Failed to connect to database after {max_retries} attempts.")
                raise

# 创建异步数据库引擎
engine = get_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    echo_pool=settings.DB_ECHO_POOL,
    future=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    connect_args={
        "server_settings": {
            "application_name": f"{settings.PROJECT_NAME}-{settings.ENVIRONMENT}",
            "statement_timeout": f"{settings.DB_STATEMENT_TIMEOUT}",
            "lock_timeout": f"{settings.DB_LOCK_TIMEOUT}"
        }
    }
)

# 创建同步数据库引擎
# 注意：需要将异步URL转换为同步URL (postgresql+asyncpg:// -> postgresql://)
sync_db_url = str(settings.DATABASE_URL).replace('+asyncpg', '')
sync_engine = create_engine(
    sync_db_url,
    echo=settings.DB_ECHO,
    echo_pool=settings.DB_ECHO_POOL,
    future=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    connect_args={
        "application_name": f"{settings.PROJECT_NAME}-{settings.ENVIRONMENT}-sync"
    }
)

# 应用SQLAlchemy监控补丁
patch_sqlalchemy_metrics()

# 重写连接生成逻辑以添加自定义错误处理
class CustomAsyncSession(AsyncSession):
    """带有增强错误处理和监控的自定义会话类"""
    
    async def execute(self, *args, **kwargs):
        """添加查询执行时间监控"""
        start = time.time()
        try:
            result = await super().execute(*args, **kwargs)
            if settings.DB_SLOW_QUERY_LOG > 0:
                duration = time.time() - start
                if duration > settings.DB_SLOW_QUERY_LOG:
                    query = str(args[0])
                    logger.warning(f"Slow query detected ({duration:.2f}s): {query[:200]}...")
            return result
        except Exception as e:
            # 记录详细的查询错误
            query = str(args[0]) if args else "Unknown query"
            logger.error(f"Database query error: {str(e)}\nQuery: {query[:500]}")
            raise

# 创建异步会话工厂
async_session_maker = sessionmaker(
    bind=engine, 
    class_=CustomAsyncSession, 
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# 创建同步会话工厂
sync_session_maker = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

def get_sync_db_session():
    """创建同步数据库会话"""
    return sync_session_maker()

async def get_db():
    """异步数据库会话生成器"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception(f"Database session error: {str(e)}")
            raise
        finally:
            await session.close()

@contextlib.contextmanager
def get_sync_db():
    """同步数据库会话上下文管理器"""
    session = get_sync_db_session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.exception(f"Sync database session error: {str(e)}")
        raise
    finally:
        session.close()

async def check_db_connection():
    """检查数据库连接是否工作正常"""
    try:
        # 不使用上下文管理器，而是显式管理连接
        conn = await engine.connect()
        try:
            result = await conn.execute(sqlalchemy.text("SELECT 1"))
            # 不要await result.fetchone()，因为它不是协程
            value = result.fetchone()
            logger.info("Database connection check: SUCCESS")
            return True
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Database connection check: FAILED - {str(e)}")
        return False

def check_sync_db_connection():
    """检查同步数据库连接是否工作正常"""
    try:
        conn = sync_engine.connect()
        try:
            result = conn.execute(sqlalchemy.text("SELECT 1"))
            value = result.fetchone()
            logger.info("Sync database connection check: SUCCESS")
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Sync database connection check: FAILED - {str(e)}")
        return False