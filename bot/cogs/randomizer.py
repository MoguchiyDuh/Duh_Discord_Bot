import random
import re
from typing import TYPE_CHECKING

import string
import secrets

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
        description="🔢 Generate a random number in the given range (defaults to 1-100).",
    )
    @app_commands.describe(
        min_value="The minimum value of the range.",
        max_value="The maximum value of the range.",
    )
    @channel_allowed(__file__)
    async def random_number(
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
            title="Random Number",
            description=f"A random number between {min_value} and {max_value}: **{random_number}**",
            color=EMBED_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    # ========== RAND CHOICE ==========
    @app_commands.command(
        name="choice",
        description="❓ Randomly choose one option from the provided list.",
    )
    @app_commands.describe(options="A comma-separated list of options to choose from.")
    @channel_allowed(__file__)
    async def random_choice(self, interaction: discord.Interaction, options: str):
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

    # ========== DICE ==========
    @app_commands.command(name="dice", description="🎲 Roll D&D dice")
    @app_commands.describe(dice="Dice notation (e.g., 1d20, 3d6+2, 4d4-1)")
    async def roll_dice(self, interaction: discord.Interaction, dice: str = "1d20"):
        """Roll dice using standard D&D notation"""
        dice_pattern = r"^(\d+)?d(\d+)([+-]\d+)?"
        match = re.match(dice_pattern, dice.lower().strip())

        if not match:
            await interaction.response.send_message(
                "❌ Invalid dice format. Examples: `1d20`, `3d6+2`, `4d4-1`",
                ephemeral=True,
            )
            return

        num_dice = int(match.group(1)) if match.group(1) else 1
        die_size = int(match.group(2))
        modifier = int(match.group(3)) if match.group(3) else 0

        if num_dice > 100 or die_size > 100:
            await interaction.response.send_message(
                "❌ Dice limits: 100 dice max, 100 sides max", ephemeral=True
            )
            return

        rolls = [random.randint(1, die_size) for _ in range(num_dice)]
        total = sum(rolls) + modifier

        critical = ""
        if num_dice == 1:
            if rolls[0] == 1:
                critical = "💥 **Critical Failure!**"
            elif rolls[0] == die_size:
                critical = "🎯 **Critical Success!**"

        result_parts = []
        if num_dice > 1:
            result_parts.append(f"🎲 **Rolls:** {', '.join(map(str, rolls))}")

        if modifier != 0:
            result_parts.append(
                f"⚖️ **Modifier:** {'+' if modifier > 0 else ''}{modifier}"
            )

        result_parts.append(f"📊 **Total:** **{total}**")

        if critical:
            result_parts.append(f"\n{critical}")

        embed_color = EMBED_COLOR
        if num_dice == 1:
            if rolls[0] == 1:
                embed_color = discord.Color.red()
            elif rolls[0] == die_size:
                embed_color = discord.Color.green()

        embed = discord.Embed(
            title="🎲 Dice Roll",
            color=embed_color,
        )
        embed.add_field(
            name=f"📝 Notation: {num_dice}d{die_size}{f'{modifier:+}' if modifier else ''}",
            value="\n".join(result_parts),
            inline=False,
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

    # ========== PASSWORD ==========
    @app_commands.command(name="password", description="🔐 Generate a secure password.")
    @app_commands.describe(
        length="Password length (12-128 characters).",
        include_uppercase="Include uppercase letters.",
        include_digits="Include digits.",
        include_special="Include special symbols.",
    )
    @channel_allowed(__file__)
    async def random_password(
        self,
        interaction: discord.Interaction,
        length: app_commands.Range[int, 12, 128] = 12,
        include_uppercase: bool = True,
        include_digits: bool = True,
        include_special: bool = True,
    ):
        """Generate a secure random password"""
        characters = string.ascii_lowercase
        if include_uppercase:
            characters += string.ascii_uppercase
        if include_digits:
            characters += string.digits
        if include_special:
            characters += string.punctuation

        if length < 12:
            raise ValueError("Password length should be at least 12 characters")

        password = [secrets.choice(characters) for _ in range(length)]
        secrets.SystemRandom().shuffle(password)
        password = "".join(password)

        embed = discord.Embed(
            title="🔐 Secure Password Generated", color=discord.Color.blue()
        )
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

    # ========== COLOR ==========
    @app_commands.command(
        name="color",
        description="🟥🟩🟦 Generate random colors with hex and RGB values.",
    )
    @app_commands.describe(count="Number of colors to generate (1-10).")
    @channel_allowed(__file__)
    async def random_color(
        self,
        interaction: discord.Interaction,
        count: app_commands.Range[int, 1, 10] = 1,
    ):
        """Generate random colors with hex and RGB values."""
        embed = discord.Embed(title="Color", color=EMBED_COLOR)

        for i in range(count):
            hex_color = f"{secrets.randbelow(256):02x}{secrets.randbelow(256):02x}{secrets.randbelow(256):02x}"

            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            color_int = int(hex_color, 16)

            embed.add_field(
                name=f"Color {i + 1}",
                value=f"**Hex:** `#{hex_color}`\n**RGB:** `rgb({r}, {g}, {b})`\n**Dec:** `{color_int}`",
                inline=True,
            )

        if count == 1:
            embed.color = discord.Color(color_int)

        await interaction.response.send_message(embed=embed)

    # ========== LOREM IPSUM ==========
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
    async def lorem_ipsum(
        self,
        interaction: discord.Interaction,
        words: app_commands.Range[int, 1, 150] = 50,
        format_type: str = "words",
    ):
        """Generate Lorem Ipsum placeholder text."""
        lorem_words = [
            "lorem",
            "ipsum",
            "dolor",
            "sit",
            "amet",
            "consectetur",
            "adipiscing",
            "elit",
            "sed",
            "do",
            "eiusmod",
            "tempor",
            "incididunt",
            "ut",
            "labore",
            "et",
            "dolore",
            "magna",
            "aliqua",
            "enim",
            "ad",
            "minim",
            "veniam",
            "quis",
            "nostrud",
            "exercitation",
            "ullamco",
            "laboris",
            "nisi",
            "aliquip",
            "ex",
            "ea",
            "commodo",
            "consequat",
            "duis",
            "aute",
            "irure",
            "in",
            "reprehenderit",
            "voluptate",
            "velit",
            "esse",
            "cillum",
            "fugiat",
            "nulla",
            "pariatur",
            "excepteur",
            "sint",
            "occaecat",
            "cupidatat",
            "non",
            "proident",
            "sunt",
            "culpa",
            "qui",
            "officia",
            "deserunt",
            "mollit",
            "anim",
            "id",
            "est",
            "laborum",
        ]
        generated_words = [random.choice(lorem_words) for _ in range(words)]

        if format_type == "words":
            text = " ".join(generated_words)
        elif format_type == "sentences":
            sentences = []
            i = 0
            while i < len(generated_words):
                length = min(random.randint(8, 15), len(generated_words) - i)
                sentence = " ".join(generated_words[i : i + length]).capitalize() + "."
                sentences.append(sentence)
                i += length
            text = " ".join(sentences)
        else:
            paragraphs = []
            i = 0
            while i < len(generated_words):
                para_sentences = []
                para_word_count = 0
                max_para_words = min(50, len(generated_words) - i)

                while para_word_count < max_para_words and i < len(generated_words):
                    length = min(random.randint(8, 15), len(generated_words) - i)
                    sentence = (
                        " ".join(generated_words[i : i + length]).capitalize() + "."
                    )
                    para_sentences.append(sentence)
                    para_word_count += length
                    i += length

                paragraphs.append(" ".join(para_sentences))
            text = "\n\n".join(paragraphs)

        text = text[0].upper() + text[1:] if text else ""
        if len(text) > 1000:
            text = text[:1000].rsplit(" ", 1)[0] + "..."

        embed = discord.Embed(title="Lorem Ipsum", color=EMBED_COLOR)
        embed.add_field(name="Generated Text", value=f"```{text}```", inline=False)
        embed.add_field(name="Words", value=str(words), inline=True)
        embed.add_field(name="Format", value=format_type.capitalize(), inline=True)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(RandomCog(bot))
