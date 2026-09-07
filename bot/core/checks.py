from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import discord
from discord import app_commands

from bot.services.channels import COG_CHANNELS


def channel_allowed(cog_file: str) -> Callable[[Any], Any]:
    cog_name = Path(cog_file).stem.lower()

    async def predicate(interaction: discord.Interaction) -> bool:
        service = getattr(interaction.client, "channels", None)
        guild = interaction.guild
        if service is None or guild is None or interaction.channel_id is None:
            raise app_commands.CheckFailure("This command is guild-only")

        if interaction.channel_id in service.allowed_channels(guild.id, cog_name):
            return True

        names = COG_CHANNELS.get(cog_name, [])
        mentions = [c.mention for c in guild.channels if c.name in names]
        if mentions:
            raise app_commands.CheckFailure(f"Command only works in: {', '.join(mentions)}")
        raise app_commands.CheckFailure(
            "Command channels are not set up yet, they will be created shortly"
        )

    return app_commands.check(predicate)
