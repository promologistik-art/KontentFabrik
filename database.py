import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from config import Config
from models import Base, HeadUser

logger = logging.getLogger(__name__)

os.makedirs(Config.DATA_DIR, exist_ok=True)

DATABASE_URL = Config.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=5, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(HeadUser).where(HeadUser.telegram_id == Config.ADMIN_ID)
        )
        if not result.scalar_one_or_none():
            session.add(HeadUser(
                telegram_id=Config.ADMIN_ID,
                username=Config.ADMIN_USERNAME,
                full_name="Admin",
                is_admin=True
            ))
            await session.commit()
            logger.info("✅ Admin created")
    
    logger.info("✅ Database initialized")