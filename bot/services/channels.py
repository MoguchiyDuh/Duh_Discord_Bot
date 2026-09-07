from __future__ import annotations

import json
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
        self._store_path = bot.settings.data_dir / "channels.json"
        self._ids: dict[str, dict[str, int]] = {}
        try:
            self._ids = json.loads(self._store_path.read_text("utf-8"))
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(
                json.dumps(self._ids, ensure_ascii=False, indent=1), "utf-8"
            )
        except OSError:
            logger.exception("Failed to persist channel id store")

    def allowed_channels(self, guild_id: int, cog_name: str) -> list[int]:
        guild_store = self._ids.get(str(guild_id), {})
        names = COG_CHANNELS.get(cog_name.lower(), [])
        return [guild_store[name] for name in names if name in guild_store]

    def channel_id(self, guild_id: int, name: str) -> int | None:
        return self._ids.get(str(guild_id), {}).get(name)

    async def ensure(self, guild: discord.Guild) -> None:
        try:
            guild_store = self._ids.setdefault(str(guild.id), {})
            commands_category = await self._ensure_category(guild, CATEGORY_COMMANDS)
            temp_category = await self._ensure_category(guild, CATEGORY_TEMP)

            for name in TEXT_CHANNELS:
                channel = await self._ensure_text_channel(guild, name, commands_category)
                guild_store[name] = channel.id

            hub = discord.utils.get(
                guild.voice_channels, name=VOICE_HUB, category=temp_category
            )
            if hub is None:
                hub = await guild.create_voice_channel(VOICE_HUB, category=temp_category)
                logger.info("Created voice channel %r in %s", VOICE_HUB, guild.name)
            guild_store[VOICE_HUB] = hub.id
            self._save()
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
    ) -> discord.TextChannel:
        channel = discord.utils.get(guild.text_channels, name=name, category=category)
        if channel is None:
            overwrite = discord.PermissionOverwrite(**_OVERWRITE_KEYS)
            channel = await guild.create_text_channel(
                name,
                category=category,
                overwrites={guild.default_role: overwrite},
            )
            logger.info("Created text channel %r in %s", name, guild.name)
        return channel
