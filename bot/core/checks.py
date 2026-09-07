from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import discord
from discord import abc, app_commands

from bot.services.channels import ChannelService


def channel_allowed(cog_file: str) -> Callable[[Any], Any]:
    cog_name = Path(cog_file).stem.lower()

    def predicate(interaction: discord.Interaction) -> bool:
        allowed = ChannelService.allowed_channels(cog_name)
        if not allowed:
            return True

        name = interaction.channel.name if isinstance(interaction.channel, abc.GuildChannel) else ""
        if name in allowed:
            return True

        mentions = []
        if interaction.guild:
            mentions = [c.mention for c in interaction.guild.channels if c.name in allowed]
        if mentions:
            raise app_commands.CheckFailure(f"Command only works in: {', '.join(mentions)}")
        raise app_commands.CheckFailure("Command not available in any channels")

    return app_commands.check(predicate)
