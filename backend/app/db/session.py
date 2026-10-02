"""
Database Session & Connection Management.
Supports PostgreSQL (asyncpg) on GCP Cloud SQL and fallback to SQLite (aiosqlite) for local dev.
"""
import os
import logging
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# Ensure local .env variables are loaded
load_dotenv()

logger = logging.getLogger("Database")

# Base class for declarative models
Base = declarative_base()

# Resolve Database URL
RAW_DB_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./orderflow.db")

# Normalize URL for asyncpg if standard postgres URL provided
if RAW_DB_URL.startswith("postgres://"):
    ASYNC_DB_URL = RAW_DB_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif RAW_DB_URL.startswith("postgresql://") and "+asyncpg" not in RAW_DB_URL:
    ASYNC_DB_URL = RAW_DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    ASYNC_DB_URL = RAW_DB_URL

# Engine configuration
engine_kwargs = {"echo": False}
if "sqlite" in ASYNC_DB_URL:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Production PostgreSQL connection pool settings for HFT throughput
    engine_kwargs.update({
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    })

engine = create_async_engine(ASYNC_DB_URL, **engine_kwargs)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    """Create tables if they don't exist."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info(f"Database initialized successfully: {ASYNC_DB_URL.split('@')[-1] if '@' in ASYNC_DB_URL else ASYNC_DB_URL}")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

async def get_db_session() -> AsyncSession:
    """Async generator providing scoped DB sessions."""
    async with async_session_factory() as session:
        yield session
