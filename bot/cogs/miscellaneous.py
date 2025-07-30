from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from . import BaseCog, channel_allowed

if TYPE_CHECKING:
    from . import MyBot


# ========= MISCELLANEOUS COG ==========
class Miscellaneous(BaseCog, commands.Cog):
    """Miscellaneous commands with channel-specific restrictions"""

    def __init__(self, bot: "MyBot"):
        super().__init__(bot)
        self.logger = bot.logger.getChild("misc")

    # ========== PING COMMAND ==========
    @app_commands.command(name="ping", description="🏓Check bot latency")
    @channel_allowed(__file__)
    async def ping(self, interaction: discord.Interaction):
        """Check the bot's response time"""
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: `{latency}ms`",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    # ========== CLEAR COMMAND ==========
    @app_commands.command(name="clear", description="🧹Delete messages")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: Optional[int] = 1):
        """Delete messages (available in any channel)"""
        amount = max(1, min(amount, 100))  # Clamp 1-100

        await interaction.response.defer(ephemeral=True)

        try:
            deleted = await interaction.channel.purge(
                limit=amount, before=interaction.created_at, bulk=True
            )
            await interaction.followup.send(
                f"🗑️ Deleted {len(deleted)} message(s)", ephemeral=True
            )
            self.logger.info(
                f"Cleared {len(deleted)} messages in #{interaction.channel.name} "
                f"by {interaction.user}"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Missing permissions to delete messages", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
            self.logger.error(f"Clear failed: {e}", exc_info=True)

    # ========== SERVER STATS ==========
    @app_commands.command(name="server-stats", description="📊View server statistics")
    @channel_allowed(__file__)
    async def server_stats(self, interaction: discord.Interaction):
        """Display server information"""
        guild = interaction.guild

        embed = discord.Embed(
            title=f"{guild.name} Statistics", color=discord.Color.blue()
        )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

        # Members
        members = guild.members
        online = sum(1 for m in members if m.status != discord.Status.offline)
        embed.add_field(
            name="👥 Members",
            value=f"Total: {guild.member_count}\nOnline: {online}",
            inline=True,
        )

        # Channels
        embed.add_field(
            name="📚 Channels",
            value=(
                f"Text: {len(guild.text_channels)}\n"
                f"Voice: {len(guild.voice_channels)}"
            ),
            inline=True,
        )

        # Server Info
        embed.add_field(
            name="ℹ️ Server",
            value=f"Created: {guild.created_at.strftime('%Y-%m-%d')}",
            inline=False,
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Miscellaneous(bot))
