from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from bot.core.bot import DuhBot

logger = logging.getLogger(__name__)

CATEGORY_COMMANDS = "Commands"
CATEGORY_TEMP = "Temporary Channels"

VOICE_HUB = "Join to Create"

TEXT_CHANNELS: tuple[str, ...] = (
    "🛠️┃bot-commands",
    "🎮┃minigames",
    "🎤┃media-hub",
)

COG_CHANNELS: dict[str, list[str]] = {
    "minigames": ["🎮┃minigames"],
    "miscellaneous": ["🛠️┃bot-commands"],
    "music": ["🎤┃media-hub"],
    "temp_channels": ["🎤┃media-hub"],
    "weather": ["🛠️┃bot-commands"],
    "randomizer": ["🛠️┃bot-commands"],
}

_OVERWRITE_KEYS = {
    "create_public_threads": False,
    "create_private_threads": False,
    "send_messages_in_threads": False,
    "use_application_commands": True,
}


class ChannelService:
    def __init__(self, bot: DuhBot) -> None:
        self.bot = bot

    @staticmethod
    def allowed_channels(cog_name: str) -> list[str]:
        return COG_CHANNELS.get(cog_name.lower(), [])

    async def ensure(self, guild: discord.Guild) -> None:
        try:
            commands_category = await self._ensure_category(guild, CATEGORY_COMMANDS)
            temp_category = await self._ensure_category(guild, CATEGORY_TEMP)

            for name in TEXT_CHANNELS:
                await self._ensure_text_channel(guild, name, commands_category)

            if not discord.utils.get(guild.voice_channels, name=VOICE_HUB, category=temp_category):
                await guild.create_voice_channel(
                    VOICE_HUB,
                    category=temp_category,
                )
                logger.info("Created voice channel %r in %s", VOICE_HUB, guild.name)
        except discord.Forbidden:
            logger.warning("Missing permissions for channel setup in %s", guild.name)
        except Exception:
            logger.exception("Channel setup failed in %s", guild.name)

    @staticmethod
    async def _ensure_category(
        guild: discord.Guild, name: str
    ) -> discord.CategoryChannel:
        if category := discord.utils.get(guild.categories, name=name):
            return category
        category = await guild.create_category(name)
        logger.info("Created category %r in %s", name, guild.name)
        return category

    async def _ensure_text_channel(
        self,
        guild: discord.Guild,
        name: str,
        category: discord.CategoryChannel,
    ) -> None:
        if discord.utils.get(guild.text_channels, name=name, category=category):
            return
        overwrite = discord.PermissionOverwrite(**_OVERWRITE_KEYS)
        await guild.create_text_channel(
            name,
            category=category,
            overwrites={guild.default_role: overwrite},
        )
        logger.info("Created text channel %r in %s", name, guild.name)
