import random
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from . import EMBED_COLOR, BaseCog, channel_allowed

if TYPE_CHECKING:
    from . import MyBot


# ========= RANDOM COG ==========
class RandomCog(BaseCog, commands.GroupCog, name="random"):
    """Commands for generating random numbers and other random utilities."""

    def __init__(self, bot: "MyBot"):
        super().__init__(bot)
        self.bot = bot
        self.logger = bot.logger.getChild("random")

    # ========== RANDINT ==========
    @app_commands.command(
        name="number",
        description="Generate a random number in the given range (defaults to 1-100).",
    )
    @app_commands.describe(
        min_value="The minimum value of the range.",
        max_value="The maximum value of the range.",
    )
    @channel_allowed(__file__)
    async def number(
        self, interaction: discord.Interaction, min_value: int = 1, max_value: int = 100
    ):
        """Generate a random number in the given range."""
        if min_value > max_value:
            await interaction.response.send_message(
                f"Error: The minimum value ({min_value}) cannot be greater than the maximum value ({max_value}).",
                ephemeral=True,
            )
            return

        random_number = random.randint(min_value, max_value)

        embed = discord.Embed(
            title="Random Number Generator",
            description=f"A random number between {min_value} and {max_value}: **{random_number}**",
            color=EMBED_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    # ========== RAND CHOICE ==========
    @app_commands.command(
        name="choice", description="Randomly choose one option from the provided list."
    )
    @app_commands.describe(options="A comma-separated list of options to choose from.")
    @channel_allowed(__file__)
    async def choice(self, interaction: discord.Interaction, options: str):
        """Randomly choose one option from the provided list."""
        options_list = [option.strip() for option in options.split(",")]

        if len(options_list) < 2:
            await interaction.response.send_message(
                "Error: Please provide at least two options separated by commas.",
                ephemeral=True,
            )
            return

        chosen_option = random.choice(options_list)

        embed = discord.Embed(
            title="Random Choice",
            description=f"I have randomly chosen: **{chosen_option}**",
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="Options Provided", value=", ".join(options_list), inline=False
        )
        await interaction.response.send_message(embed=embed)

    # ========== FLIP A COIN ==========
    @app_commands.command(
        name="coinflip", description="Flip a coin and get either Heads or Tails."
    )
    @channel_allowed(__file__)
    async def coinflip(self, interaction: discord.Interaction):
        """Flip a coin and get either Heads or Tails."""
        result = random.choice(["Heads", "Tails"])

        embed = discord.Embed(
            title="Coin Flip",
            description=f"The coin landed on: **{result}**",
            color=EMBED_COLOR,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(RandomCog(bot))
