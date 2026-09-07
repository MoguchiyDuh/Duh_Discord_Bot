from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.bot import DuhBot
from bot.core.checks import channel_allowed

EMBED_COLOR = discord.Color.blurple()


class BaseCog(commands.Cog):
    def __init__(self, bot: DuhBot) -> None:
        self.bot = bot
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        send = (
            interaction.followup.send
            if interaction.response.is_done()
            else interaction.response.send_message
        )
        if isinstance(error, app_commands.CheckFailure):
            await send(f"❌ {error}", ephemeral=True)
        elif isinstance(error, app_commands.CommandInvokeError):
            self.logger.error(
                "Command error in %s", self.__class__.__name__, exc_info=error.original
            )
            await send("❌ An error occurred while executing this command", ephemeral=True)
        else:
            self.logger.error("Unexpected error in %s: %s", self.__class__.__name__, error)
            await send("❌ An unexpected error occurred", ephemeral=True)


__all__ = ["BaseCog", "EMBED_COLOR", "channel_allowed"]
