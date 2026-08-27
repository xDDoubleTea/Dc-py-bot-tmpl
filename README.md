# Discord bot template

[![CI](https://github.com/xDDoubleTea/Dc-py-bot-tmpl/actions/workflows/ci.yml/badge.svg)](https://github.com/xDDoubleTea/Dc-py-bot-tmpl/actions/workflows/ci.yml)

A starting point for a `discord.py` bot with an async SQLAlchemy database layer,
cog-based commands, structured logging and graceful shutdown.

## VS Code

**This repository ships a `.vscode/` directory, so read it before opening the
project in VS Code.** Workspace settings override your own for this folder, and
opening it will prompt you to install the recommended extensions.

`.vscode/settings.json` sets:

- Ruff as the Python formatter, on save, with fix and organize-imports actions
- pytest discovery for the built-in Testing panel, pointed at `tests/`
- `.venv` as the interpreter and Pylance in `standard` type-checking mode

`.vscode/extensions.json` recommends Ruff, the Python extensions, Even Better
TOML and the GitHub Actions extension, and marks `ms-python.isort` unwanted,
since ruff sorts imports through its `I` rules.

Delete the directory if you would rather keep your own setup; nothing else in
the template depends on it.

## Features

- Using `uv` as the python virtual environment manager, written in `rust`!
- Using `discord.py` as the discord bot framework
- Using `sqlalchemy` for ORM database
- Slash commands organised into cogs, auto-loaded from `cogs/`
- Rotating file + console logs, and a shutdown path that closes the gateway and
  disposes the database engine on `SIGINT` / `SIGTERM`

## Setup

```bash
git clone https://github.com/xDDoubleTea/Dc-py-bot-tmpl
cd Dc-py-bot-tmpl
uv sync

# Remember to copy the .env.example to .env and fill in your bot token and the database url

uv run main.py
```

Run `main.py` from the repository root: cogs are discovered with a relative path,
and the default SQLite file lives at `./db/test.db`.

Before the first run, set your own IDs in `config/constants.py`:

| Name | Meaning |
| --- | --- |
| `command_prefix` | Prefix for the text commands in `cogs/admin.py` |
| `MY_GUILD` | Guild that slash commands are synced to on startup |
| `DEV_ID` | Your user ID, used by the `is_me_command` / `is_me_app_command` checks |
| `LOG_DIR` | Directory for `bot.log` and `sqlalchemy.log` |

`.env` holds the secrets:

| Variable | Meaning |
| --- | --- |
| `BOT_TOKEN` | Your bot's token |
| `DATABASE_URL` | SQLAlchemy async URL, e.g. `sqlite+aiosqlite:///./db/test.db` |
| `DEBUG` | `True` for debug logging and SQL echo; anything else is off |

`DATABASE_URL` must name an async driver (`sqlite+aiosqlite`, `postgresql+asyncpg`),
since the engine is created with `create_async_engine`.

## Layout

```
cogs/       commands, one cog per file, loaded automatically at startup
config/     constants, secrets, logging setup
db/         Base, models, and the session manager
utils/      permission checks, error handlers, and Discord object helpers
logs/       bot.log and sqlalchemy.log, rotated at midnight, 7 days kept (see LOG_DIR)
```

## Using the database

`MyBot.setup_hook` creates one `AsyncDatabaseManager` and stores it on the bot, so
every cog reaches it through `self.bot.database_manager`. It is an async context
manager that hands out a session:

```python
async with self.bot.database_manager as session:
    await session.execute(statement)
```

Leaving the block commits, or rolls back if the body raised, and closes the
session either way. Sessions are tracked per asyncio task, so commands running
concurrently each get their own.

The sessionmaker uses `expire_on_commit=False`, so model instances loaded inside
the block are still readable after it.

### Adding a model

Define it against `Base` in `db/example.py` (or a new module in `db/`):

```python
from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class MyModel(Base):
    __tablename__ = "my_table"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
```

Use `BigInteger` for Discord IDs, which do not fit in a 32-bit `INTEGER`.

If the model lives in a new module, import it in `main.py` next to the existing
model imports. `Base.metadata.create_all` only creates tables for models that have
been imported by the time it runs.

Tables are created at startup and there is no migration tool, so changing a model
means deleting `db/test.db` and letting it be recreated.

## Example: the settings cog

`cogs/settings.py` is a worked example of the patterns above: a per-guild
key/value store backed by the `guild_settings` table, with the primary key on
`(guild_id, key)`.

| Command | What it does | Pattern it shows |
| --- | --- | --- |
| `/settings set <key> <value>` | Saves a value for this server | SQLite upsert, so setting the same key twice updates it |
| `/settings get <key>` | Shows one setting | Single-row `select` with `session.scalar` |
| `/settings list` | Shows every setting for this server | Multi-row `session.scalars`, rendered as an embed |
| `/settings reset [key]` | Deletes one setting, or all of them | `delete()` and reading `result.rowcount` |

All four are administrator-only through `is_administrator()` from `utils/checks.py`.
A refused check is answered by the global error handler, so the cog carries no
error handling of its own.

The keys live in the `SETTING_KEYS` dict at the top of the file, which drives the
autocomplete choices and records the type of each value. Channel and role settings
store the object's ID and resolve it on read with `try_get_channel` /
`try_get_role` from `utils/discord_utils.py`, so a renamed channel keeps working.

`/settings set` validates the value against the key's type before writing, so the
table only holds values that resolve. Channel and role keys accept a mention or a
raw ID and check that the object exists in the server; text keys are checked
against the column's 512-character limit. A value that fails raises
`InvalidSettingValue`, and the command replies with the reason as an ephemeral
message without touching the database.

To add a setting, add an entry to `SETTING_KEYS`:

```python
SETTING_KEYS: dict[str, str] = {
    "welcome_channel": "channel",
    "log_channel": "channel",
    "mod_role": "role",
    "greeting": "text",
    "report_channel": "channel",  # new
}
```

Delete `cogs/settings.py` and the `GuildSetting` model once you no longer need the
example.

## Writing a cog

Every file in `cogs/` ending in `.py` is loaded at startup. A cog looks like:

```python
import logging

import discord
from discord import app_commands
from discord.ext import commands

from main import MyBot

logger = logging.getLogger(__name__)


class MyCog(commands.Cog):
    def __init__(self, bot: MyBot):
        self.bot = bot

    @app_commands.command(name="hello", description="Say hello")
    async def hello(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hello!")


async def setup(bot: MyBot) -> None:
    await bot.add_cog(MyCog(bot))
```

`cogs/admin.py` provides owner-only text commands to `>load`, `>unload` and
`>reload` cogs while the bot is running, plus `>sync_app_commands` to re-sync the
command tree.

`cogs/help.py` builds `/help` from the command tree. Mark a command as
`extras={"hidden": True}` to keep it out of that listing.

### Permission checks

`utils/checks.py` provides:

| Check | Applies to | Raises |
| --- | --- | --- |
| `is_me_command()` | Text commands | `IsNotDev` |
| `is_me_app_command()` | Slash commands | `IsNotDev` |
| `is_administrator()` | Slash commands | `UserNotAdministrator` |

`is_administrator()` allows the bot owner and any guild administrator, and denies
in DMs. Both exceptions carry a `.message`, which the global error handler replies
with, so a guarded command needs no handler of its own.

## Error handling

`utils/error_handlers.py` answers errors from both command families:

- `ErrorHandlingTree`, passed to the bot as `tree_cls`, handles slash commands
- `handle_command_error`, wired up as `MyBot.on_command_error`, handles text commands

Failed checks, cooldowns and missing permissions get a specific reply, ephemeral
for slash commands. Anything else is logged with a traceback and answered with a
generic message. `CommandNotFound` is ignored, so a mistyped prefix stays quiet.

Add a per-command `.error` handler only when a command needs a reply of its own;
otherwise it is handled for you.

To add a case, extend `app_command_message` for slash commands or the chain in
`handle_command_error` for text commands. Returning `None` from
`app_command_message` marks the error as a bug, which logs it and sends the
generic reply.

`IsNotDev` inherits from both `CommandError` and `AppCommandError`, since only
`AppCommandError` subclasses reach `CommandTree.on_error`.

## Development

Run this before pushing; CI runs the same three commands and fails on any of
them:

```bash
uv run ruff format .
uv run ruff check --fix .
uv run pytest
```

`ruff format` owns line length, `ruff check` covers the rule set in
`pyproject.toml`, and the tests live in `tests/`. Tests use an in-memory
database and stubbed Discord objects, so none of them need a bot token or a
gateway connection.

## Logging

`setup_logger` writes to the console and to `bot.log`, rotating at midnight and
keeping 7 days. SQL statements go to `sqlalchemy.log` separately. Both live in the
directory named by `LOG_DIR` in `config/constants.py`. Get a logger in any module
with `logging.getLogger(__name__)`.

The log level follows `debug` in `config/secrets.py`, read from the `DEBUG`
environment variable, which also switches on SQL echoing for the engine.

## Roadmap

Ideas for building on the template:

- **Migrations** — add `alembic` so model changes do not mean deleting the
  database.
- **Postgres** — swap `DATABASE_URL` to `postgresql+asyncpg://...` and add
  `asyncpg`. The upsert in `cogs/settings.py` is SQLite-specific and becomes
  `sqlalchemy.dialects.postgresql.insert`.
- **A repository layer** — move queries out of the cogs into modules under `db/`,
  so commands call `get_setting(guild_id, key)` instead of building statements.
- **Guild-aware settings** — read `guild_settings` from a listener, for example a
  welcome message posted to the stored `welcome_channel` on `on_member_join`.
- **Global command sync** — `setup_hook` syncs to `MY_GUILD` for instant updates
  while developing; sync globally once the bot is in more than one server.
- **Caching** — keep hot settings in memory and invalidate on write, to avoid a
  query per command.
- **Tests** — run the cogs against an in-memory
  `sqlite+aiosqlite:///:memory:` engine.
- **Deployment** — a `systemd` unit or container image. `SIGTERM` is already
  handled, so a supervisor can stop the bot cleanly.
