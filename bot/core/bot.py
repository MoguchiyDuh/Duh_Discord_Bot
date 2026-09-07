from __future__ import annotations

import logging
import pkgutil
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot.services.channels import ChannelService
from bot.services.lyrics import LyricsService
from bot.services.youtube import YouTube

if TYPE_CHECKING:
    from bot.core.config import Settings

logger = logging.getLogger(__name__)


class DuhBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.presences = True
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self.channels: ChannelService | None = None
        self.youtube: YouTube | None = None
        self.lyrics: LyricsService | None = None

    async def setup_hook(self) -> None:
        self.channels = ChannelService(self)
        self.youtube = YouTube(self.settings)
        self.lyrics = LyricsService(self.settings)

        loaded = await self.load_cogs()
        logger.info("Loaded %d cogs: %s", len(loaded), ", ".join(loaded))

        if self.settings.sync_guild_id:
            guild = discord.Object(id=self.settings.sync_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(
                "Synced %d commands to guild %d", len(synced), self.settings.sync_guild_id
            )
        else:
            synced = await self.tree.sync()
            logger.info("Synced %d global commands", len(synced))

    async def load_cogs(self) -> list[str]:
        import bot.cogs as cogs_package

        loaded: list[str] = []
        for module_info in pkgutil.iter_modules(cogs_package.__path__):
            if module_info.name.startswith("_"):
                continue
            extension = f"bot.cogs.{module_info.name}"
            try:
                await self.load_extension(extension)
                loaded.append(module_info.name)
            except Exception:
                logger.exception("Failed to load extension %s", extension)
        return loaded

    async def on_ready(self) -> None:
        if self.user:
            logger.info(
                "Logged in as %s (ID: %d), %d guild(s)", self.user, self.user.id, len(self.guilds)
            )
        if self.channels:
            for guild in self.guilds:
                await self.channels.ensure(guild)
