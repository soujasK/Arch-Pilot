"""
Pytest configuration and shared fixtures.
"""
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app

# ---------------------------------------------------------------------------
# In-memory SQLite engine for tests (no PostgreSQL needed)
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="session")
async def setup_test_db():
    """Create all tables once per test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(setup_test_db) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean transactional scope for each test."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with overridden DB dependency."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def sync_client(db_session: AsyncSession) -> Generator:
    """Synchronous test client for simple endpoint checks."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_github_service():
    """Mock GitHub service for unit tests that don't touch the network."""
    service = MagicMock()
    service.fetch_repository_metadata = AsyncMock(return_value={
        "name": "test-repo",
        "owner": "test-owner",
        "description": "A test repository",
        "language": "Python",
        "stars": 42,
        "url": "https://github.com/test-owner/test-repo",
    })
    service.fetch_file_tree = AsyncMock(return_value=[
        {"path": "main.py", "type": "blob"},
        {"path": "utils/helpers.py", "type": "blob"},
        {"path": "utils/auth.py", "type": "blob"},
    ])
    service.fetch_file_content = AsyncMock(return_value="import os\n")
    return service


SAMPLE_ADJ_LIST: dict[str, list[str]] = {
    "main.py": ["utils/helpers.py", "utils/auth.py"],
    "utils/helpers.py": ["utils/auth.py"],
    "utils/auth.py": [],
    "orphan.py": [],
}

CYCLIC_ADJ_LIST: dict[str, list[str]] = {
    "a.py": ["b.py"],
    "b.py": ["c.py"],
    "c.py": ["a.py"],
    "d.py": ["e.py"],
    "e.py": [],
}
