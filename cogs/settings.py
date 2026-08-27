"""
Example: using the database from a cog.

A per-guild settings store, backed by the `guild_settings` table (db/example.py).
Every command here demonstrates one SQL pattern you will need in a real bot:

    /settings set     -> upsert (insert, or update if the row already exists)
    /settings get     -> single-row SELECT, plus resolving a stored ID into an object
    /settings list    -> multi-row SELECT scoped to one guild
    /settings reset   -> DELETE, and how to tell how many rows went away

The session comes from `self.bot.database_manager`, which commits when the
`async with` block exits normally and rolls back if the body raises.
"""

import logging
from typing import Sequence

import discord
from discord import Interaction, app_commands
from discord.app_commands.errors import AppCommandError
from discord.ext import commands
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from db.example import GuildSetting
from main import MyBot
from utils.checks import UserNotAdministrator, is_administrator
from utils.discord_utils import try_get_channel, try_get_role

logger = logging.getLogger(__name__)

# The settings this bot understands. Keeping them in one place means the keys can be
# offered as Choices (Discord autocompletes them, and users cannot invent new ones),
# and it records how each value should be rendered when it is read back.
#   "channel" / "role" -> the value is an ID; resolve it against the guild on read
#   "text"             -> the value is shown as-is
SETTING_KEYS: dict[str, str] = {
    "welcome_channel": "channel",
    "log_channel": "channel",
    "mod_role": "role",
    "greeting": "text",
}

KEY_CHOICES = [app_commands.Choice(name=key, value=key) for key in SETTING_KEYS]


class Settings(commands.Cog):
    def __init__(self, bot: MyBot):
        self.bot = bot

    # A Group turns these into subcommands: /settings set, /settings get, ...
    group = app_commands.Group(
        name="settings",
        description="Read and write this server's saved settings",
        guild_only=True,
    )

    async def _render(self, guild: discord.Guild, key: str, value: str) -> str:
        """Turn a stored value back into something readable in Discord."""
        kind = SETTING_KEYS.get(key, "text")
        if kind == "text":
            return value

        # Channels and roles are stored as IDs, never as names: names change, IDs do
        # not. try_get_* checks the cache first and only then hits the API.
        try:
            object_id = int(value)
        except ValueError:
            return f"invalid value: `{value}`"

        if kind == "channel":
            channel = await try_get_channel(guild, object_id)
            if channel is None:
                return f"deleted channel (`{object_id}`)"
            return channel.mention

        role = await try_get_role(guild, object_id)
        if role is None:
            return f"deleted role (`{object_id}`)"
        return role.mention

    @group.command(name="set", description="Save a setting for this server")
    @app_commands.describe(
        key="Which setting to change",
        value="The new value. For channel/role settings, mention the channel or role.",
    )
    @app_commands.choices(key=KEY_CHOICES)
    @is_administrator()
    async def set_setting(
        self, interaction: Interaction, key: app_commands.Choice[str], value: str
    ) -> None:
        assert interaction.guild is not None  # guaranteed by guild_only=True

        # An INSERT alone would fail the second time a key is set, because
        # (guild_id, key) is the primary key. The upsert tells SQLite to overwrite the
        # existing row's value instead of raising, which makes the command idempotent.
        statement = (
            sqlite_upsert(GuildSetting)
            .values(guild_id=interaction.guild.id, key=key.value, value=value)
            .on_conflict_do_update(
                index_elements=[GuildSetting.guild_id, GuildSetting.key],
                set_={"value": value},
            )
        )

        async with self.bot.database_manager as session:
            await session.execute(statement)
        # The commit happened on the way out of the block above.

        rendered = await self._render(interaction.guild, key.value, value)
        await interaction.response.send_message(f"Set `{key.value}` to {rendered}.")

    @group.command(name="get", description="Show one of this server's settings")
    @app_commands.describe(key="Which setting to read")
    @app_commands.choices(key=KEY_CHOICES)
    @is_administrator()
    async def get_setting(
        self, interaction: Interaction, key: app_commands.Choice[str]
    ) -> None:
        assert interaction.guild is not None

        statement = select(GuildSetting).where(
            GuildSetting.guild_id == interaction.guild.id,
            GuildSetting.key == key.value,
        )
        setting = None
        async with self.bot.database_manager as session:
            # scalar() returns the single model instance, or None if there is no row.
            setting = await session.scalar(statement)

        # expire_on_commit=False on the sessionmaker is what lets us keep reading
        # `setting`'s attributes out here, after the session has been closed.
        if setting is None:
            await interaction.response.send_message(
                f"`{key.value}` is not set for this server."
            )
            return

        rendered = await self._render(interaction.guild, setting.key, setting.value)
        await interaction.response.send_message(f"`{setting.key}` is {rendered}.")

    @group.command(name="list", description="Show every setting saved for this server")
    @is_administrator()
    async def list_settings(self, interaction: Interaction) -> None:
        assert interaction.guild is not None

        # Always filter by guild_id: the table holds rows for every server the bot is
        # in, and forgetting the filter would leak another server's configuration.
        statement = (
            select(GuildSetting)
            .where(GuildSetting.guild_id == interaction.guild.id)
            .order_by(GuildSetting.key)
        )

        settings: Sequence[GuildSetting] = []
        async with self.bot.database_manager as session:
            settings = (await session.scalars(statement)).all()

        if len(settings) == 0:
            await interaction.response.send_message(
                "No settings saved for this server yet."
            )
            return

        embed = discord.Embed(
            title=f"Settings for {interaction.guild.name}",
            color=discord.Color.blue(),
        )
        for setting in settings:
            rendered = await self._render(
                interaction.guild, setting.key, setting.value
            )
            embed.add_field(name=setting.key, value=rendered, inline=False)

        await interaction.response.send_message(embed=embed)

    @group.command(name="reset", description="Delete one setting, or all of them")
    @app_commands.describe(key="Leave empty to delete every setting for this server")
    @app_commands.choices(key=KEY_CHOICES)
    @is_administrator()
    async def reset_settings(
        self, interaction: Interaction, key: app_commands.Choice[str] | None = None
    ) -> None:
        assert interaction.guild is not None

        statement = delete(GuildSetting).where(
            GuildSetting.guild_id == interaction.guild.id
        )
        if key is not None:
            statement = statement.where(GuildSetting.key == key.value)

        deleted = 0
        async with self.bot.database_manager as session:
            result = (await session.execute(statement)).all()
            # rowcount is read inside the block, while the result is still attached
            # to the live session.
            deleted = result.count

        logger.info(
            f"Reset {deleted} setting(s) for guild {interaction.guild.id} "
            f"by {interaction.user.id}."
        )
        target = "all settings" if key is None else f"`{key.value}`"
        await interaction.response.send_message(
            f"Deleted {deleted} row(s) for {target}."
        )

    # The is_administrator() check raises UserNotAdministrator, an AppCommandError.
    # Without a handler discord.py logs it as an unhandled exception and the user just
    # sees the interaction fail, so every guarded command gets one.
    @set_setting.error
    @get_setting.error
    @list_settings.error
    @reset_settings.error
    async def on_settings_error(
        self, interaction: Interaction, error: AppCommandError
    ) -> None:
        if isinstance(error, UserNotAdministrator):
            await interaction.response.send_message(error.message, ephemeral=True)
            return

        logger.exception("Unhandled error in the settings cog", exc_info=error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Something went wrong running that command.", ephemeral=True
            )


async def setup(bot: MyBot) -> None:
    await bot.add_cog(Settings(bot))
