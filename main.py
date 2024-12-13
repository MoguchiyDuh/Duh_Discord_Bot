import asyncio
import os
import discord
from discord.ext import commands
from utils.config import DISCORD_TOKEN

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        sync_commands = await bot.tree.sync()
        print(f"{len(sync_commands)} commands synced")
    except Exception as e:
        print(f"Failed to sync commands {e}")


async def load():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and filename != "__init__.py":
            await bot.load_extension(f"cogs.{filename[:-3]}")
    print("Loaded cogs: " + ", ".join(bot.extensions))


async def main():
    async with bot:
        await load()
        await bot.start(DISCORD_TOKEN)


asyncio.run(main())
