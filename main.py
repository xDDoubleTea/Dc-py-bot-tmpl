import discord
import logging
from discord.ext import commands
from sqlalchemy.ext.asyncio import create_async_engine
from config.constants import command_prefix, MY_GUILD
from config.secrets import bot_token, DATABASE_URL
import asyncio
from db.async_db_manager import AsyncDatabaseManager
from db.base import Base

# Models must be imported before Base.metadata.create_all() runs below, otherwise
# they are not registered on the metadata yet and no tables get created. The cogs
# import them too, but that happens later, inside setup_hook().
from db.example import GuildSetting, User  # noqa: F401
from config.secrets import debug
from config.logger import setup_logger
from utils.error_handlers import ErrorHandlingTree, handle_command_error
import signal
import os

logger = logging.getLogger(__name__)

# Change this to your bot's intents

intents = discord.Intents.all()


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=command_prefix,
            intents=intents,
            tree_cls=ErrorHandlingTree,
        )

        self.engine = create_async_engine(
            DATABASE_URL, echo=debug, hide_parameters=True
        )
        self.database_manager: AsyncDatabaseManager

    async def setup_hook(self) -> None:
        self.database_manager: AsyncDatabaseManager = AsyncDatabaseManager(
            self, self.engine
        )

        for cog in os.listdir("cogs"):
            if cog.endswith(".py"):
                await self.load_extension(f"cogs.{cog[:-3]}")
                
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        await handle_command_error(ctx, error)

    async def close(self) -> None:
        # engine.dispose() must run even if the gateway teardown above raises or is
        # cancelled: aiosqlite's connection workers are non-daemon threads, so an
        # undisposed engine leaves the interpreter hanging in threading._shutdown().
        try:
            await super().close()
        finally:
            await self.engine.dispose()

    async def on_ready(self):

        logger.info(f"Logged in as {self.user}!")


async def main():
    if debug:
        setup_logger(log_level=logging.DEBUG)
    else:
        setup_logger(log_level=logging.INFO)

    bot = MyBot()

    main_task = asyncio.current_task()
    assert main_task is not None
    stopping = False

    def request_stop(sig: signal.Signals) -> None:
        """
        Ask the bot to shut down, once.

        Only this task is cancelled: bot.close() already tears down discord.py's
        gateway, heartbeat and HTTP tasks in the right order, so cancelling every
        task would just interrupt that cleanup half-way. The `stopping` guard means
        a second Ctrl+C cannot re-cancel a shutdown that is already running.
        """
        nonlocal stopping
        if stopping:
            logger.warning(
                f"Received {sig.name} again; shutdown already in progress..."
            )
            return

        stopping = True
        logger.info(f"Received exit signal {sig.name}...")
        main_task.cancel()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, request_stop, sig)

    async with bot.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        # Leaving this block always calls bot.close(), on every exit path.
        async with bot:
            await bot.start(token=bot_token)
    except asyncio.CancelledError:
        logger.info("Bot shutdown initiated...")
    except Exception as e:
        logger.exception("An unhandled error occurred:", exc_info=e)
    finally:
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
