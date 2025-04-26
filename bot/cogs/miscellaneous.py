from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.logger import BASE_LOG_FILE_NAME, setup_logger

logger = setup_logger(
    name="miscellaneous", log_to_file=True, log_file=BASE_LOG_FILE_NAME
)


class Miscellaneous(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Ping the bot")
    async def ping(self, interaction: discord.Interaction):
        """Checks the bot's latency."""
        latency = round(interaction.client.latency * 1000)
        embed = discord.Embed(
            title="Pong! 🏓",
            description=f"Latency: `{latency}ms`",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clear", description="Clear")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: Optional[int] = 1):
        """Delete the last N messages in the current channel"""
        await interaction.response.defer(ephemeral=True)

        # Validate amount
        amount = min(max(1, amount), 100)  # Clamp between 1-100

        try:
            # Fetch and delete messages
            deleted = await interaction.channel.purge(
                limit=amount, before=interaction.created_at, bulk=True
            )

            # Send confirmation (ephemeral)
            await interaction.followup.send(
                f"🗑️ Deleted {len(deleted)} message(s)", ephemeral=True
            )

            # Log action
            logger.info(
                f"Cleared {len(deleted)} messages in #{interaction.channel.name} "
                f"by {interaction.user} in {interaction.guild.name}"
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to delete messages here", ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ Failed to delete messages: {e}", ephemeral=True
            )
            logger.error(f"Clear command failed: {e}")


async def setup(bot):
    await bot.add_cog(Miscellaneous(bot))
