from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs import EMBED_COLOR, BaseCog

if TYPE_CHECKING:
    from bot.core.bot import DuhBot

logger = logging.getLogger(__name__)

CATEGORIES: dict[str, dict[str, Any]] = {
    "overview": {
        "title": "🤖 Duh Discord Bot - Overview",
        "description": "A multipurpose Discord bot with music, games, and utilities to enhance your server experience!",
        "commands": [
            "💡 /help - Show this interactive help menu",
            "🔒 Commands are restricted to specific channels for organization",
            "📋 Use the dropdown menu below to explore different categories",
            "⚡ Type '/' in any channel to see what commands are available there",
        ],
        "footer": "✨ Select a category from the dropdown to see specific commands!",
    },
    "music": {
        "title": "🎵 Music Commands",
        "description": "🎧 Transform your server into a concert hall! Play music from YouTube with complete queue management.",
        "commands": [
            "➕ /music join - Join your voice channel",
            "▶️ /music play <query> - Play music (YouTube URL, playlist, or search!)",
            "⏸️ /music pause - Pause the current track",
            "▶️ /music resume - Resume playback",
            "⏭️ /music skip [range] - Skip tracks (e.g. skip, skip 3, skip 1-5)",
            "📜 /music queue - See what's coming up next",
            "🎵 /music current - What's playing right now?",
            "🔀 /music shuffle - Shuffle your queue",
            "🔁 /music loop - Repeat the current track",
            "🧹 /music clear - Clear the entire queue",
            "📝 /music lyrics [song] - Get lyrics for a song",
            "🚪 /music leave - Leave the voice channel",
        ],
        "footer": "🌟 Supports YouTube URLs, playlists, and any search terms!",
    },
    "minigames": {
        "title": "🎮 Fun & Games",
        "description": "🏆 Challenge your friends to classic games!",
        "commands": [
            "♟️ /minigames chess @opponent - Battle it out in chess",
            "❌⭕ /minigames tic-tac-toe @opponent - Quick and classic",
            "🔴🟡 /minigames connect4 @opponent - Drop your way to victory",
        ],
        "footer": "🎯 Games create private threads with interactive buttons!",
    },
    "random": {
        "title": "🎲 Random Generators",
        "description": "🎯 Need to make a decision? Want some randomness?",
        "commands": [
            "🔢 /random number [min] [max] - Random numbers (default 1-100)",
            "❓ /random choice <options> - Pick from a comma-separated list",
            "🎲 /random dice <dice> - Roll D&D style dice (1d20, 3d6+2, 4d4-1)",
            "🪙 /random coinflip - Heads or tails?",
            "🔐 /random password [length] - Secure passwords (12-128 chars)",
            "🟥🟩🟦 /random color [count] - Random colors with hex & RGB (1-10)",
            "📝 /random lorem_ipsum [words] [format] - Placeholder text",
        ],
        "footer": "🔒 Passwords use cryptographically secure randomness!",
    },
    "temp_channels": {
        "title": "🔊 Voice Channel Commands",
        "description": "Manage your temporary voice channels.",
        "commands": [
            "Join 'Join to Create' to get a temp channel",
            "🔒 /temp_channels lock - Lock your channel",
            "🔓 /temp_channels unlock - Unlock your channel",
            "👥 /temp_channels limit <number> - Set user limit (0-99)",
            "🏷️ /temp_channels rename <name> - Rename your channel",
            "💬 /temp_channels set-status <status> - Set channel status",
            "👢 /temp_channels kick @user - Kick user from your channel",
            "🔇 /temp_channels mute @user - Mute user in your channel",
            "🔊 /temp_channels unmute @user - Unmute user",
        ],
        "footer": "Only channel owners can use these commands",
    },
    "weather": {
        "title": "🌤️ Weather Information",
        "description": "☀️ Current weather anywhere in the world!",
        "commands": ["⛅ /weather <city> - Current weather conditions for any city"],
        "footer": "🆓 Uses Open-Meteo API - free and no API key required!",
    },
    "miscellaneous": {
        "title": "⚙️ Utility Commands",
        "description": "🛠️ Essential server management tools and bot utilities.",
        "commands": [
            "🏓 /ping - Check bot latency",
            "📊 /server-stats - View server statistics",
            "🧹 /clear [amount] - Delete messages (1-100, requires Manage Messages)",
        ],
        "footer": "🔐 Some commands require special permissions",
    },
}

CATEGORY_ORDER = (
    "overview",
    "music",
    "minigames",
    "random",
    "temp_channels",
    "weather",
    "miscellaneous",
)


class HelpSelect(discord.ui.Select["HelpView"]):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label={
                    "overview": "Overview",
                    "music": "Music",
                    "minigames": "Minigames",
                    "random": "Generators",
                    "temp_channels": "Voice Channels",
                    "weather": "Weather",
                    "miscellaneous": "Utilities",
                }[key],
                description=CATEGORIES[key]["description"][:100],
                emoji={
                    "overview": "🏠",
                    "music": "🎵",
                    "minigames": "🎮",
                    "random": "🎲",
                    "temp_channels": "🔊",
                    "weather": "🌤️",
                    "miscellaneous": "⚙️",
                }[key],
                value=key,
            )
            for key in CATEGORY_ORDER
        ]
        super().__init__(
            placeholder="Select a category to explore commands...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        embed = build_embed(self.values[0])
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=120)
        self.message: discord.InteractionMessage | None = None
        self.select = HelpSelect()
        self.add_item(self.select)

    async def on_timeout(self) -> None:
        self.select.disabled = True
        if self.message:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)


def build_embed(category: str = "overview") -> discord.Embed:
    data = CATEGORIES[category]
    embed = discord.Embed(
        title=data["title"],
        description=data["description"],
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Available Commands", value="\n".join(data["commands"]), inline=False
    )
    embed.set_footer(text=data["footer"])
    return embed


class HelpCog(BaseCog):
    def __init__(self, bot: DuhBot) -> None:
        super().__init__(bot)

    @app_commands.command(name="help", description="❓ Show help menu with all available commands")
    async def help_command(self, interaction: discord.Interaction) -> None:
        view = HelpView()
        await interaction.response.send_message(embed=build_embed(), view=view, ephemeral=True)
        view.message = await interaction.original_response()


async def setup(bot: DuhBot) -> None:
    await bot.add_cog(HelpCog(bot))
