import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENV", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://solidcare:solidcare@localhost:5432/solidcare_test",
)

from app.config import get_settings
from app.database import get_db
from app.main import app

get_settings.cache_clear()
from app.config import settings  # noqa: E402 — reload after cache clear

TEST_DATABASE_URL = os.environ.get("DATABASE_URL", settings.DATABASE_URL)


@pytest_asyncio.fixture
async def test_engine():
    import app.database as db_module

    engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False
    )
    db_module.engine = engine
    db_module.AsyncSessionLocal = session_factory
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
