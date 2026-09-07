from __future__ import annotations

import logging
import random
import re
import secrets
import string
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs import EMBED_COLOR, BaseCog, channel_allowed

if TYPE_CHECKING:
    from bot.core.bot import DuhBot

logger = logging.getLogger(__name__)

DICE_PATTERN = re.compile(r"^(\d{1,3})?d(\d{1,3})([+-]\d{1,4})?$")
LOREM_WORDS: tuple[str, ...] = (
    "lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit",
    "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore", "et", "dolore",
    "magna", "aliqua", "enim", "ad", "minim", "veniam", "quis", "nostrud",
    "exercitation", "ullamco", "laboris", "nisi", "aliquip", "ex", "ea", "commodo",
    "consequat", "duis", "aute", "irure", "in", "reprehenderit", "voluptate",
    "velit", "esse", "cillum", "fugiat", "nulla", "pariatur", "excepteur", "sint",
    "occaecat", "cupidatat", "non", "proident", "sunt", "culpa", "qui", "officia",
    "deserunt", "mollit", "anim", "id", "est", "laborum",
)


class RandomCog(BaseCog, commands.GroupCog, name="random"):
    def __init__(self, bot: DuhBot) -> None:
        super().__init__(bot)

    @app_commands.command(
        name="number",
        description="🔢 Generate a random number in the given range (defaults to 1-100).",
    )
    @app_commands.describe(
        min_value="The minimum value of the range.",
        max_value="The maximum value of the range.",
    )
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def random_number(
        self, interaction: discord.Interaction, min_value: int = 1, max_value: int = 100
    ) -> None:
        if min_value > max_value:
            await interaction.response.send_message(
                f"❌ The minimum value ({min_value}) cannot be greater than the maximum value ({max_value}).",
                ephemeral=True,
            )
            return
        number = random.randint(min_value, max_value)
        embed = discord.Embed(
            title="Random Number",
            description=f"A random number between {min_value} and {max_value}: **{number}**",
            color=EMBED_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="choice",
        description="❓ Randomly choose one option from the provided list.",
    )
    @app_commands.describe(options="A comma-separated list of options to choose from.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def random_choice(self, interaction: discord.Interaction, options: str) -> None:
        options_list = [option.strip() for option in options.split(",") if option.strip()]
        if len(options_list) < 2:
            await interaction.response.send_message(
                "❌ Please provide at least 2 options separated by commas.", ephemeral=True
            )
            return
        if len(options_list) > 100:
            await interaction.response.send_message("❌ Too many options (max 100).", ephemeral=True)
            return

        chosen = random.choice(options_list)
        embed = discord.Embed(
            title="Random Choice",
            description=f"I have randomly chosen: **{chosen}**",
            color=EMBED_COLOR,
        )
        embed.add_field(name="Options Provided", value=", ".join(options_list)[:1024], inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="dice", description="🎲 Roll D&D dice")
    @app_commands.describe(dice="Dice notation (e.g., 1d20, 3d6+2, 4d4-1)")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def roll_dice(self, interaction: discord.Interaction, dice: str = "1d20") -> None:
        match = DICE_PATTERN.match(dice.lower().strip())
        if not match:
            await interaction.response.send_message(
                "❌ Invalid dice format. Examples: `1d20`, `3d6+2`, `4d4-1`", ephemeral=True
            )
            return

        num_dice = int(match.group(1)) if match.group(1) else 1
        die_size = int(match.group(2))
        modifier = int(match.group(3)) if match.group(3) else 0

        rolls = [random.randint(1, die_size) for _ in range(num_dice)]
        total = sum(rolls) + modifier

        critical = ""
        if num_dice == 1 and rolls[0] == 1:
            critical = "💥 **Critical Failure!**"
        elif num_dice == 1 and rolls[0] == die_size:
            critical = "🎯 **Critical Success!**"

        parts: list[str] = []
        if num_dice > 1:
            parts.append(f"🎲 **Rolls:** {', '.join(map(str, rolls))}")
        if modifier != 0:
            parts.append(f"⚖️ **Modifier:** {'+' if modifier > 0 else ''}{modifier}")
        parts.append(f"📊 **Total:** **{total}**")
        if critical:
            parts.append(critical)

        color = EMBED_COLOR
        if num_dice == 1 and rolls[0] == 1:
            color = discord.Color.red()
        elif num_dice == 1 and rolls[0] == die_size:
            color = discord.Color.green()

        notation = f"{num_dice}d{die_size}{f'{modifier:+}' if modifier else ''}"
        embed = discord.Embed(title="🎲 Dice Roll", color=color)
        embed.add_field(name=f"📝 Notation: {notation}", value="\n".join(parts), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip", description="🪙 Flip a coin.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def coinflip(self, interaction: discord.Interaction) -> None:
        result = random.choice(["Heads", "Tails"])
        embed = discord.Embed(
            title="Coin Flip",
            description=f"The coin landed on: **{result}**",
            color=EMBED_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="password", description="🔐 Generate a secure password.")
    @app_commands.describe(
        length="Password length (12-128 characters).",
        include_uppercase="Include uppercase letters.",
        include_digits="Include digits.",
        include_special="Include special symbols.",
    )
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def random_password(
        self,
        interaction: discord.Interaction,
        length: app_commands.Range[int, 12, 128] = 12,
        include_uppercase: bool = True,
        include_digits: bool = True,
        include_special: bool = True,
    ) -> None:
        alphabet = string.ascii_lowercase
        if include_uppercase:
            alphabet += string.ascii_uppercase
        if include_digits:
            alphabet += string.digits
        if include_special:
            alphabet += string.punctuation

        password = "".join(secrets.choice(alphabet) for _ in range(length))
        embed = discord.Embed(title="🔐 Secure Password Generated", color=discord.Color.blue())
        embed.add_field(name="Your Password", value=f"||`{password}`||", inline=False)
        embed.add_field(
            name="Specifications",
            value=(
                f"**Length:** {length}\n"
                f"**Contains:** "
                f"{'A-Z, ' if include_uppercase else ''}"
                f"{'0-9, ' if include_digits else ''}"
                f"{'!@#, ' if include_special else ''}"
                "a-z"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="color",
        description="🟥🟩🟦 Generate random colors with hex and RGB values.",
    )
    @app_commands.describe(count="Number of colors to generate (1-10).")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def random_color(
        self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 10] = 1
    ) -> None:
        embed = discord.Embed(title="Color", color=EMBED_COLOR)
        for i in range(count):
            value = secrets.randbits(24)
            embed.add_field(
                name=f"Color {i + 1}",
                value=(
                    f"**Hex:** `#{value:06x}`\n"
                    f"**RGB:** `rgb({value >> 16}, {(value >> 8) & 0xFF}, {value & 0xFF})`\n"
                    f"**Dec:** `{value}`"
                ),
                inline=True,
            )
        if count == 1:
            embed.color = discord.Color(secrets.randbits(24))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="lorem_ipsum", description="📝 Generate Lorem Ipsum placeholder text."
    )
    @app_commands.describe(
        words="Number of words to generate (1-150).",
        format_type="Output format (words, sentences, paragraphs).",
    )
    @app_commands.choices(
        format_type=[
            app_commands.Choice(name="Words", value="words"),
            app_commands.Choice(name="Sentences", value="sentences"),
            app_commands.Choice(name="Paragraphs", value="paragraphs"),
        ]
    )
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def lorem_ipsum(
        self,
        interaction: discord.Interaction,
        words: app_commands.Range[int, 1, 150] = 50,
        format_type: str = "words",
    ) -> None:
        generated = [random.choice(LOREM_WORDS) for _ in range(words)]

        if format_type == "words":
            text = " ".join(generated)
        elif format_type == "sentences":
            sentences = []
            i = 0
            while i < len(generated):
                length = min(random.randint(8, 15), len(generated) - i)
                sentences.append(" ".join(generated[i : i + length]).capitalize() + ".")
                i += length
            text = " ".join(sentences)
        else:
            paragraphs = []
            i = 0
            while i < len(generated):
                para_sentences = []
                remaining = min(50, len(generated) - i)
                while remaining > 0:
                    length = min(random.randint(8, 15), remaining)
                    para_sentences.append(" ".join(generated[i : i + length]).capitalize() + ".")
                    remaining -= length
                    i += length
                paragraphs.append(" ".join(para_sentences))
            text = "\n\n".join(paragraphs)

        text = text[:1000].rsplit(" ", 1)[0] + "…" if len(text) > 1000 else text

        embed = discord.Embed(title="Lorem Ipsum", color=EMBED_COLOR)
        embed.add_field(name="Generated Text", value=f"```\n{text}\n```", inline=False)
        embed.add_field(name="Words", value=str(words), inline=True)
        embed.add_field(name="Format", value=format_type.capitalize(), inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot: DuhBot) -> None:
    await bot.add_cog(RandomCog(bot))
