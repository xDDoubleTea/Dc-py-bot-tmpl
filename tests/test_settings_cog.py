"""
Tests for the settings cog's logic.

The value parsing and rendering are the parts worth testing: they decide what
reaches the database and what the user sees. Neither needs a gateway connection,
only a stand-in guild and stubbed lookups.
"""

from types import SimpleNamespace

import pytest

from cogs.settings import InvalidSettingValue, Settings
from tests.conftest import CHANNEL_ID, ROLE_ID


@pytest.fixture
def cog(monkeypatch):
    """
    The cog with its Discord lookups stubbed out.

    try_get_channel / try_get_role are imported into cogs.settings, so that is the
    name to replace; only CHANNEL_ID and ROLE_ID resolve.
    """

    async def fake_get_channel(guild, channel_id):
        if channel_id == CHANNEL_ID:
            return SimpleNamespace(mention=f"<#{channel_id}>", name="general")
        return None

    async def fake_get_role(guild, role_id):
        if role_id == ROLE_ID:
            return SimpleNamespace(mention=f"<@&{role_id}>", name="Moderator")
        return None

    monkeypatch.setattr("cogs.settings.try_get_channel", fake_get_channel)
    monkeypatch.setattr("cogs.settings.try_get_role", fake_get_role)

    return Settings(SimpleNamespace())


@pytest.mark.parametrize(
    "raw",
    [
        f"<#{CHANNEL_ID}>",  # what Discord inserts when a channel is picked
        str(CHANNEL_ID),  # an ID pasted by hand
        f"  <#{CHANNEL_ID}>  ",  # stray whitespace
    ],
)
async def test_channel_values_are_stored_as_ids(cog, fake_guild, raw):
    assert await cog._parse_value(fake_guild, "welcome_channel", raw) == str(CHANNEL_ID)


async def test_role_values_are_stored_as_ids(cog, fake_guild):
    assert await cog._parse_value(fake_guild, "mod_role", f"<@&{ROLE_ID}>") == str(
        ROLE_ID
    )


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        ("welcome_channel", "#general", "expects a channel"),
        ("welcome_channel", "not a channel", "expects a channel"),
        ("welcome_channel", "<@&123>", "expects a channel"),  # wrong mention type
        ("mod_role", f"<#{CHANNEL_ID}>", "expects a role"),
        ("welcome_channel", "<#999999999999999999>", "exists in this server"),
        ("greeting", "   ", "cannot be set to an empty value"),
        ("greeting", "x" * 600, "holds at most"),
    ],
)
async def test_invalid_values_are_refused(cog, fake_guild, key, raw, expected):
    """Nothing reaches the database unless it resolves; the reason is shown."""
    with pytest.raises(InvalidSettingValue) as error:
        await cog._parse_value(fake_guild, key, raw)

    assert expected in error.value.message


async def test_text_values_are_stored_verbatim(cog, fake_guild):
    assert await cog._parse_value(fake_guild, "greeting", "  Welcome!  ") == "Welcome!"


async def test_stored_ids_render_as_mentions(cog, fake_guild):
    assert await cog._render(fake_guild, "welcome_channel", str(CHANNEL_ID)) == (
        f"<#{CHANNEL_ID}>"
    )
    assert await cog._render(fake_guild, "mod_role", str(ROLE_ID)) == f"<@&{ROLE_ID}>"


async def test_deleted_objects_render_without_crashing(cog, fake_guild):
    """A channel can be deleted after it was saved."""
    assert "deleted channel" in await cog._render(
        fake_guild, "welcome_channel", "999999999999999999"
    )
