"""Tests for the global error handlers."""

from types import SimpleNamespace

import pytest
from discord import app_commands
from discord.ext import commands

from utils.checks import IsNotDev, UserNotAdministrator
from utils.error_handlers import app_command_message, handle_command_error


def test_is_not_dev_reaches_both_handlers():
    """
    Only AppCommandError subclasses reach CommandTree.on_error, and only
    CommandError subclasses reach on_command_error. IsNotDev is raised by a check
    in each family, so it has to be both.
    """
    error = IsNotDev()

    assert isinstance(error, app_commands.AppCommandError)
    assert isinstance(error, commands.CommandError)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (UserNotAdministrator(), UserNotAdministrator().message),
        (IsNotDev(), IsNotDev().message),
        (app_commands.MissingPermissions(["manage_guild"]), "manage_guild"),
        (app_commands.BotMissingPermissions(["send_messages"]), "send_messages"),
        (app_commands.CheckFailure("nope"), "cannot use that command"),
    ],
)
def test_expected_errors_get_a_specific_reply(error, expected):
    message = app_command_message(error)

    assert message is not None
    assert expected in message


def test_unexpected_errors_are_treated_as_bugs():
    """None means 'log it and send the generic reply' rather than 'say nothing'."""
    unexpected = app_commands.CommandInvokeError(
        SimpleNamespace(name="settings set"), ValueError("kaboom")
    )

    assert app_command_message(unexpected) is None


@pytest.fixture
def ctx():
    """Stands in for commands.Context, recording whatever gets sent."""
    sent = []

    async def send(message):
        sent.append(message)

    return SimpleNamespace(
        send=send,
        sent=sent,
        command=SimpleNamespace(qualified_name="load"),
        prefix=">",
    )


async def test_unknown_commands_stay_quiet(ctx):
    """A mistyped prefix should not make the bot answer."""
    await handle_command_error(ctx, commands.CommandNotFound())

    assert ctx.sent == []


async def test_failed_check_explains_itself(ctx):
    await handle_command_error(ctx, IsNotDev())

    assert ctx.sent == [IsNotDev().message]


async def test_cooldown_reports_the_wait(ctx):
    await handle_command_error(ctx, commands.CommandOnCooldown(None, 12.4, None))

    assert "12s" in ctx.sent[0]


async def test_unexpected_error_gets_a_generic_reply(ctx, caplog):
    await handle_command_error(ctx, commands.CommandInvokeError(RuntimeError("boom")))

    assert ctx.sent == ["Something went wrong running that command."]
    # The real cause belongs in the log, not in the channel.
    assert "boom" in caplog.text
