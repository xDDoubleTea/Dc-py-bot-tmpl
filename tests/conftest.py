"""
Shared test fixtures.

The bot's modules read their configuration at import time, so the environment has
to be populated before anything under config/ is imported. setdefault is used so a
real .env or exported variable still wins locally.
"""

import os

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DEBUG", "False")

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from db.async_db_manager import AsyncDatabaseManager
from db.base import Base
from db.example import GuildSetting, User  # noqa: F401

GUILD_ID = 1039906085626196079
CHANNEL_ID = 1245973831190056991
ROLE_ID = 987654321098765432


@pytest.fixture
async def engine():
    """A fresh in-memory database, with the schema created."""
    # StaticPool keeps every connection pointed at the same in-memory database;
    # without it each connection would get its own empty one.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
def database_manager(engine):
    """The session manager the cogs use, wired to the test database."""
    return AsyncDatabaseManager(SimpleNamespace(), engine)


@pytest.fixture
def fake_guild():
    """Stands in for discord.Guild; only id and name are ever read."""
    return SimpleNamespace(id=GUILD_ID, name="Test Guild")
