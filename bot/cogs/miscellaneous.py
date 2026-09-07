from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs import BaseCog, channel_allowed

if TYPE_CHECKING:
    from bot.core.bot import DuhBot

logger = logging.getLogger(__name__)


class Miscellaneous(BaseCog, commands.Cog):
    def __init__(self, bot: DuhBot) -> None:
        super().__init__(bot)

    @app_commands.command(name="ping", description="🏓 Check bot latency")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: `{latency}ms`",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clear", description="🧹 Delete messages")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def clear(
        self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100] = 1
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await interaction.channel.purge(
                limit=amount, before=interaction.created_at, bulk=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Missing permissions to delete messages", ephemeral=True
            )
            return
        except discord.HTTPException as exc:
            logger.error("Purge failed: %s", exc)
            await interaction.followup.send(f"❌ Error: {exc}", ephemeral=True)
            return

        await interaction.followup.send(f"🗑️ Deleted {len(deleted)} message(s)", ephemeral=True)
        logger.info(
            "Cleared %d messages in #%s by %s",
            len(deleted),
            getattr(interaction.channel, "name", "unknown"),
            interaction.user,
        )

    @app_commands.command(name="server-stats", description="📊 View server statistics")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def server_stats(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        embed = discord.Embed(title=f"{guild.name} Statistics", color=discord.Color.blue())
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

        online = sum(1 for m in guild.members if m.status != discord.Status.offline)
        embed.add_field(
            name="👥 Members",
            value=f"Total: {guild.member_count}\nOnline: {online}",
            inline=True,
        )
        embed.add_field(
            name="📚 Channels",
            value=f"Text: {len(guild.text_channels)}\nVoice: {len(guild.voice_channels)}",
            inline=True,
        )
        embed.add_field(
            name="ℹ️ Server",
            value=f"Created: {guild.created_at.strftime('%Y-%m-%d')}",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: DuhBot) -> None:
    await bot.add_cog(Miscellaneous(bot))
