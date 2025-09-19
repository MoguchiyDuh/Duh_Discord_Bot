import logging
import os
from typing import Dict, List, Optional, Type, TypeVar

import discord
from discord.abc import GuildChannel
from discord.ext import commands

# class NotAllowed


T = TypeVar("T", bound="ChannelService")


class ChannelService:
    COMMAND_CATEGORIES = ["Commands", "Temporary Channels"]

    COMMAND_CHANNELS = {
        "minigames": ["🎮┃minigames"],
        "miscellaneous": ["🛠️┃bot-commands"],
        "music": ["🎤┃media-hub"],
        "generandom": ["🛠️┃bot-commands"],
        "temp_channels": ["🎤┃media-hub"],
        "voice_hub": ["Join to Create"],
        "weather": ["🛠️┃bot-commands"],
        "randomizer": ["🛠️┃bot-commands"],
    }

    CHANNEL_CONFIG = {
        "🛠️┃bot-commands": {
            "type": "text",
            "category": COMMAND_CATEGORIES[0],
            "overwrites": {
                "default_role": {
                    "create_public_threads": False,
                    "create_private_threads": False,
                    "send_messages_in_threads": False,
                    "use_application_commands": True,
                }
            },
        },
        "🎮┃minigames": {
            "type": "text",
            "category": COMMAND_CATEGORIES[0],
            "overwrites": {
                "default_role": {
                    "create_public_threads": False,
                    "create_private_threads": False,
                    "send_messages_in_threads": False,
                    "use_application_commands": True,
                }
            },
        },
        "🎤┃media-hub": {
            "type": "text",
            "category": COMMAND_CATEGORIES[0],
            "overwrites": {
                "default_role": {
                    "create_public_threads": False,
                    "create_private_threads": False,
                    "send_messages_in_threads": False,
                    "use_application_commands": True,
                }
            },
        },
        "Join to Create": {
            "type": "voice",
            "category": COMMAND_CATEGORIES[1],
            "overwrites": {},
        },
    }

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger: logging.Logger = bot.logger

    @classmethod
    async def create(cls: Type[T], bot: commands.Bot) -> T:
        """Factory method for creating and initializing the service"""
        instance = cls(bot)
        return instance

    @classmethod
    def get_channel_name(cls, cog_name: str) -> List:
        """Get the configured channel name for a cog (you may use __file__)"""
        filename = os.path.basename(cog_name)
        cog_name = os.path.splitext(filename)[0].lower()
        return cls.COMMAND_CHANNELS.get(cog_name, [])

    async def ensure_channels(
        self, guild: discord.Guild
    ) -> Dict[str, Optional[GuildChannel]]:
        """Ensure all required channels exist with proper configuration"""
        results = {}

        try:
            categories = await self._ensure_categories(guild)

            for name, config in self.CHANNEL_CONFIG.items():
                category_name = config["category"]
                if not isinstance(category_name, str):
                    category_name = category_name.name

                config["category"] = categories[category_name]
                results[name] = await self._ensure_channel(guild, name, config)

        except discord.Forbidden:
            self.logger.warning(f"Missing permissions in {guild.name}")
        except Exception as e:
            self.logger.error(
                f"Channel setup failed in {guild.name}: {e}", exc_info=True
            )

        return results

    async def _ensure_categories(
        self, guild: discord.Guild
    ) -> Dict[str, discord.CategoryChannel]:
        """Ensure all required categories exist"""
        return {
            name: await self._ensure_category(guild, name)
            for name in self.COMMAND_CATEGORIES
        }

    async def _ensure_category(
        self, guild: discord.Guild, name: str
    ) -> discord.CategoryChannel:
        """Get or create a category channel"""
        if category := discord.utils.get(guild.categories, name=name):
            return category

        category = await guild.create_category(name)
        self.logger.info(f"Created category: {name}")
        return category

    async def _ensure_channel(
        self, guild: discord.Guild, name: str, config: dict
    ) -> Optional[GuildChannel]:
        """Ensure a channel exists with correct configuration"""
        if channel := discord.utils.get(
            guild.channels, name=name, category=config.get("category")
        ):
            return channel

        return await self._create_channel(guild, name, config)

    async def _create_channel(
        self, guild: discord.Guild, name: str, config: dict
    ) -> GuildChannel:
        """Create a new channel with full configuration"""
        overwrites = self._create_overwrites(guild, config.get("overwrites", {}))
        create_args = {
            "name": name,
            "category": config.get("category"),
            "overwrites": overwrites,
        }

        creator = (
            guild.create_text_channel
            if config["type"] == "text"
            else guild.create_voice_channel
        )

        channel = await creator(**create_args)
        self.logger.info(f"Created channel: {name}")
        return channel

    def _create_overwrites(self, guild: discord.Guild, overwrite_config: dict) -> dict:
        """Generate complete permission overwrites"""
        overwrites = {}

        for role_key, permissions in overwrite_config.items():
            target = (
                guild.default_role
                if role_key == "default_role"
                else discord.utils.find(
                    lambda r: r.name.lower() == role_key.lower(), guild.roles
                )
            )

            if not target and role_key != "default_role":
                self.logger.warning(
                    f"Role '{role_key}' not found in guild '{guild.name}'"
                )
                continue

            overwrites[target] = discord.PermissionOverwrite(**permissions)

        return overwrites
