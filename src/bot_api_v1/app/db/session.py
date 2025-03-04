
# bot_api_v1/app/db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import contextlib
from bot_api_v1.app.core.config import settings

# 创建异步PostgreSQL数据库引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    future=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
)

# 创建异步会话工厂
async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

@contextlib.asynccontextmanager
async def get_db():
    """异步会话上下文管理器"""
    session = async_session_maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()