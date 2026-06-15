import pytest
import pytest_asyncio

import app.register_models  # noqa: F401

from app.database import Base
from tests.conftest import test_engine


@pytest_asyncio.fixture
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
