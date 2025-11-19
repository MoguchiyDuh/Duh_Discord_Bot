import asyncio
import os
from typing import List

import discord
from discord.ext import commands

from bot.services.channel_service import ChannelService
from bot.utils.config import DISCORD_TOKEN
from bot.utils.logger import setup_logger


class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        super().__init__(command_prefix="!", intents=intents)

        self.logger = setup_logger(name="bot")
        self.channel_service = None

    async def setup_hook(self):
        """Initialize bot services and load extensions"""
        self.channel_service = await ChannelService.create(self)

        loaded = await self.load_cogs()
        self.logger.info(f"Loaded {len(loaded)} cogs: {', '.join(loaded)}")

        try:
            sync_commands = await self.tree.sync()
            self.logger.info(f"Synced {len(sync_commands)} commands.")
        except Exception as e:
            self.logger.exception(f"Failed to sync commands: {e}")

    async def ensure_channels(self):
        """Ensure channels exist in all guilds"""
        for guild in self.guilds:
            try:
                if self.channel_service:
                    await self.channel_service.ensure_channels(guild)
            except discord.Forbidden:
                self.logger.warning(f"Missing permissions in {guild.name}")
            except Exception as e:
                self.logger.error(f"Channel error in {guild.name}: {e}", exc_info=True)

    async def load_cogs(self) -> List[str]:
        """Dynamically load all cogs from the cogs directory"""
        loaded = []
        cog_dir = os.path.join(os.path.dirname(__file__), "cogs")

        for filename in os.listdir(cog_dir):
            if (
                filename.endswith(".py")
                and not filename.startswith("_")
                and "disabled" not in filename.lower()
            ):
                cog_name = f"bot.cogs.{filename[:-3]}"
                try:
                    await self.load_extension(cog_name)
                    loaded.append(filename[:-3])
                except Exception as e:
                    self.logger.error(f"Failed to load {cog_name}: {e}")

        return loaded

    async def on_ready(self) -> None:
        """Confirm successful login"""
        if self.user:
            self.logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
            self.logger.info(f"Connected to {len(self.guilds)} guilds")
        await self.ensure_channels()

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Clean up resources when bot is removed from a guild"""
        self.logger.info(f"Removed from guild: {guild.name} (ID: {guild.id})")

        # Clean up music players
        music_cog = self.get_cog("Music")
        if music_cog and hasattr(music_cog, "players"):
            player = music_cog.players.pop(guild.id, None)
            if player and player.voice_client:
                await player.voice_client.disconnect()

        # Clean up temp channels
        temp_channel_cog = self.get_cog("TempChannels")
        if temp_channel_cog and hasattr(temp_channel_cog, "temp_channels"):
            temp_channel_cog.temp_channels.pop(guild.id, None)


async def main():
    bot = MyBot()
    try:
        await bot.start(DISCORD_TOKEN)  # type: ignore
    except Exception as e:
        bot.logger.critical(f"Fatal error: {e}")
        raise
    finally:
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Keyboard Interrupt detected, exiting...")
