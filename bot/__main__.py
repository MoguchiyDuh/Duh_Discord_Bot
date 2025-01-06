import os
import discord
import asyncio
from discord.ext import commands

from bot.utils.config import DISCORD_TOKEN

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    """Event handler when the bot is ready."""
    print(f"Logged in as {bot.user}")
    try:
        # Syncing commands
        sync_commands = await bot.tree.sync()
        print(f"Synced {len(sync_commands)} commands.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


async def run_bot():
    """Load cogs and start the bot."""
    try:
        # await bot.load_extension("bot.cogs.ready")
        await bot.load_extension("bot.cogs.music")
        await bot.load_extension("bot.cogs.temp_channels")
        await bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"Unexpected error occurred: {e}")
    finally:
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())  # Run the bot using asyncio
    except KeyboardInterrupt:
        print("Keyboard Interrupt detected, exiting...")
