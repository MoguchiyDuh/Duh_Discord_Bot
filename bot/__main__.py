import asyncio
import os

import discord
from discord.ext import commands

from bot.utils.config import DISCORD_TOKEN
from bot.utils.logger import BASE_LOG_FILE_NAME, setup_logger

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

base_logger = setup_logger(name="bot", log_to_file=True, log_file=BASE_LOG_FILE_NAME)


@bot.event
async def on_ready():
    """Event handler when the bot is ready."""
    base_logger.info(f"Logged in as {bot.user}")
    try:
        sync_commands = await bot.tree.sync()
        base_logger.info(f"Synced {len(sync_commands)} commands.")
    except Exception as e:
        base_logger.exception(f"Failed to sync commands: {e}")


async def load_cogs():
    """Load all cogs from the cogs directory."""
    cog_directory = os.path.join(os.path.dirname(__file__), "cogs")
    cogs_loaded = []

    for filename in os.listdir(cog_directory):
        if (
            filename.endswith(".py")
            and filename != "__init__.py"
            and "disabled" not in filename.lower()
        ):
            cog_name = f"bot.cogs.{filename[:-3]}"
            try:
                await bot.load_extension(cog_name)
                cogs_loaded.append(cog_name)
            except Exception as e:
                base_logger.info(f"Failed to load cog {cog_name}: {e}")

    return cogs_loaded


async def run_bot():
    """Load cogs and start the bot."""
    try:
        loaded_cogs = await load_cogs()
        base_logger.info(f"Loaded cogs: {loaded_cogs}")
        await bot.start(DISCORD_TOKEN)
    except Exception as e:
        base_logger.exception(f"Error occurred: {e}")
    finally:
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())  # Run the bot using asyncio
    except KeyboardInterrupt:
        print("Keyboard Interrupt detected, exiting...")
