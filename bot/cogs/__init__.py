"""
Core initialization for cogs, providing base classes and utilities.
"""

from typing import TYPE_CHECKING, Dict, Callable, Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.services.channel_service import ChannelService
from bot.utils.logger import setup_logger

if TYPE_CHECKING:
    from bot.__main__ import MyBot

EMBED_COLOR: discord.Color = discord.Color.blurple()


class BaseCog(commands.Cog):
    """Base Cog with global error handling for all commands."""

    def __init__(self, bot: "MyBot") -> None:
        self.bot: "MyBot" = bot
        self.channel_service: ChannelService = ChannelService(bot)
        self.logger = setup_logger("cogs")

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Global error handler for all cog commands"""
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(f"❌ {str(error)}", ephemeral=True)
        elif isinstance(error, app_commands.CommandInvokeError):
            self.logger.error(
                f"Command error in {self.__class__.__name__}: {error.original}",
                exc_info=True,
            )
            await interaction.response.send_message(
                "❌ An error occurred while executing this command", ephemeral=True
            )
        else:
            self.logger.error(f"Unexpected error in {self.__class__.__name__}: {error}")
            await interaction.response.send_message(
                "❌ An unexpected error occurred", ephemeral=True
            )


# ========== CUSTOM CHECK DECORATOR ==========


def channel_allowed(cog_name: str) -> Callable[[Any], Any]:
    """Decorator to restrict commands to specific channels"""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not cog_name:
            return True

        # Type ignore or assumption here as interaction.client is strictly Client | None
        channel_service: ChannelService = interaction.client.channel_service  # type: ignore
        current_channel = interaction.channel.name if interaction.channel else ""

        if any(
            current_channel == channel_name
            for channel_name in channel_service.get_channel_name(cog_name)
        ):
            return True

        # Collect allowed channels
        allowed_channels = []
        for channel_name in channel_service.get_channel_name(cog_name):
            channel = (
                discord.utils.get(interaction.guild.channels, name=channel_name)
                if interaction.guild
                else None
            )
            if channel:
                allowed_channels.append(channel.mention)

        # Error message with mentions
        if not allowed_channels:
            raise app_commands.CheckFailure("Command not available in any channels")

        raise app_commands.CheckFailure(
            f"Command only works in: {', '.join(allowed_channels)}"
        )

    return app_commands.check(predicate)


# ========== MEDIA SETTINGS ==========
DISCORD_FFMPEG_OPTIONS: Dict[str, str] = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}
