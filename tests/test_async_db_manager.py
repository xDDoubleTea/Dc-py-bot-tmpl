"""Tests for the session manager every cog uses."""

import asyncio

import pytest
from sqlalchemy import select

from db.example import GuildSetting
from tests.conftest import GUILD_ID


async def test_commits_on_success(database_manager):
    async with database_manager as session:
        session.add(GuildSetting(guild_id=GUILD_ID, key="greeting", value="hi"))

    # A second block only sees the row if the first one committed on the way out.
    async with database_manager as session:
        stored = await session.scalar(select(GuildSetting))

    assert stored is not None
    assert stored.value == "hi"


async def test_rolls_back_when_the_body_raises(database_manager):
    with pytest.raises(ValueError):
        async with database_manager as session:
            session.add(GuildSetting(guild_id=GUILD_ID, key="greeting", value="hi"))
            raise ValueError("something went wrong")

    async with database_manager as session:
        rows = (await session.scalars(select(GuildSetting))).all()

    assert len(rows) == 0


async def test_exception_reaches_the_caller(database_manager):
    """The manager must not swallow what the command raised."""
    with pytest.raises(ValueError, match="boom"):
        async with database_manager:
            raise ValueError("boom")


async def test_concurrent_blocks_get_separate_sessions(database_manager):
    """
    The manager is shared by every cog, so overlapping commands must not end up
    sharing one session.
    """
    sessions = []

    async def write(index: int):
        async with database_manager as session:
            sessions.append(session)
            # Yield control so the tasks genuinely interleave inside their blocks.
            await asyncio.sleep(0)
            session.add(
                GuildSetting(guild_id=GUILD_ID, key=f"key{index}", value=str(index))
            )

    await asyncio.gather(*(write(i) for i in range(10)))

    assert len({id(s) for s in sessions}) == 10

    async with database_manager as session:
        rows = (await session.scalars(select(GuildSetting))).all()

    assert len(rows) == 10


async def test_nested_blocks_unwind_in_order(database_manager):
    async with database_manager as outer:
        async with database_manager as inner:
            assert inner is not outer
        # Leaving the inner block must not have closed the outer one.
        assert await outer.scalar(select(GuildSetting)) is None
