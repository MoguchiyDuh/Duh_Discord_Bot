import discord
from discord import app_commands
from discord.ext import commands


class Miscellaneous(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =======================PING=======================
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


async def setup(bot):
    await bot.add_cog(Miscellaneous(bot))
