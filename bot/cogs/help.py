import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View

from . import EMBED_COLOR, BaseCog


class HelpSelect(Select):
    def __init__(self, create_embed_func):
        self.create_embed_func = create_embed_func
        options = [
            discord.SelectOption(
                label="Overview",
                description="Bot introduction and basic info",
                emoji="🏠",
                value="overview",
            ),
            discord.SelectOption(
                label="Music",
                description="Play music and manage queues",
                emoji="🎵",
                value="music",
            ),
            discord.SelectOption(
                label="Minigames",
                description="Play interactive games",
                emoji="🎮",
                value="minigames",
            ),
            discord.SelectOption(
                label="Generators",
                description="Random content generators",
                emoji="🎲",
                value="random",
            ),
            discord.SelectOption(
                label="Voice Channels",
                description="Manage temporary voice channels",
                emoji="🔊",
                value="temp_channels",
            ),
            discord.SelectOption(
                label="Weather",
                description="Get weather information",
                emoji="🌤️",
                value="weather",
            ),
            discord.SelectOption(
                label="Utilities",
                description="Server management tools",
                emoji="⚙️",
                value="miscellaneous",
            ),
        ]
        super().__init__(
            placeholder="Select a category to explore commands...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        embed = self.create_embed_func(category)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(View):
    def __init__(self, create_embed_func):
        super().__init__(timeout=120)
        self.add_item(HelpSelect(create_embed_func))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)


class HelpCog(BaseCog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger.getChild("help")
        self.categories = {
            "overview": {
                "title": "🤖 Duh Discord Bot - Overview",
                "description": "A multipurpose Discord bot with music, games, and utilities to enhance your server experience!",
                "commands": [
                    "💡 /help - Show this interactive help menu",
                    "🔒 Commands are restricted to specific channels for organization",
                    "📋 Use dropdown menu below to explore different categories",
                    "⚡ Type '/' in any channel to see what commands are available there",
                ],
                "footer": "✨ Select a category from the dropdown to see specific commands and start having fun!",
            },
            "music": {
                "title": "🎵 Music Commands",
                "description": "🎧 Transform your server into a concert hall! Play music from YouTube with complete queue management.",
                "commands": [
                    "➕ /music join - Join your voice channel and get ready to rock!",
                    "▶️ /music play <query> - Play music (YouTube URL, playlist, or search anything!)",
                    "⏸️ /music pause - Take a breather, pause the current track",
                    "▶️ /music resume - Back to the music! Resume playback",
                    "⏭️ /music skip [range] - Skip tracks (examples: skip, skip 3, skip 1-5)",
                    "📜 /music queue - See what's coming up next in your playlist",
                    "🎵 /music current - What's playing right now?",
                    "🔀 /music shuffle - Mix things up! Shuffle your queue",
                    "🔁 /music loop - Repeat that amazing track over and over",
                    "🧹 /music clear - Start fresh, clear the entire queue",
                    "📝 /music lyrics [song] - Sing along! Get lyrics for any song",
                    "🚪 /music leave - Time to go, leave the voice channel",
                ],
                "footer": "🌟 Supports YouTube/SoundCloud URLs, playlists, and any search terms you can think of!",
            },
            "minigames": {
                "title": "🎮 Fun & Games",
                "description": "🏆 Challenge your friends to classic games! Perfect for breaking the ice or settling debates.",
                "commands": [
                    "♟️ /minigames chess @opponent - Battle it out in a game of chess",
                    "❌⭕ /minigames tic-tac-toe @opponent - Quick and classic tic-tac-toe",
                    "🔴🔴🔴🔴 /minigames connect4 @opponent - Drop your way to victory in Connect Four",
                ],
                "footer": "🎯 Games create private threads with interactive buttons - no need to type moves!",
            },
            "random": {
                "title": "🎲 Random Generators",
                "description": "🎯 Need to make a decision? Want some randomness? These tools have got you covered!",
                "commands": [
                    "🔢 /random number [min] [max] - Generate random numbers (default 1-100)",
                    "❓ /random choice <options> - Can't decide? List your options separated by commas!",
                    "🎲 /random dice <dice> - Roll D&D style dice (examples: 1d20, 3d6+2, 4d4-1)",
                    "  /random coinflip - Heads or tails? Let fate decide!",
                    "🔐 /random password [length] [include_uppercase] [include_digits] [include_special] - Generate secure passwords (12-128 chars)",
                    "🟥🟩🟦 /random color [count] - Beautiful random colors with hex & RGB values (1-10 colors)",
                    "📝 /random lorem_ipsum [words] [format_type] - Generate placeholder text for your projects",
                ],
                "footer": "🔒 All generators use cryptographically secure randomness - truly unpredictable!",
            },
            "temp_channels": {
                "title": "Voice Channel Commands",
                "description": "Manage your temporary voice channels.",
                "commands": [
                    "Join 'Join to Create' voice channel to create temp channel",
                    "🔒 /temp_channels lock - Lock your channel",
                    "🔓 /temp_channels unlock - Unlock your channel",
                    "👥 /temp_channels limit <number> - Set user limit (0-99)",
                    "🏷️ /temp_channels rename <name> - Rename your channel",
                    "  /temp_channels set-status <status> - Set channel status",
                    "👢 /temp_channels kick @user - Kick user from your channel",
                    "🔇 /temp_channels mute @user - Mute user in your channel",
                    "🔊 /temp_channels unmute @user - Unmute user",
                ],
                "footer": "Only channel owners can use these commands",
            },
            "weather": {
                "title": "🌤️ Weather Information",
                "description": "☀️ Stay informed about the weather anywhere in the world! Perfect for planning activities or just satisfying curiosity.",
                "commands": [
                    "⛅ /weather <city> - Get current weather conditions for any city worldwide"
                ],
                "footer": "🆓 Uses Open-Meteo API - completely free and no API key required!",
            },
            "miscellaneous": {
                "title": "⚙️ Utility Commands",
                "description": "🛠️ Essential server management tools and bot utilities to keep everything running smoothly.",
                "commands": [
                    "🏓 /ping - Check how fast the bot responds (latency test)",
                    "📊 /server-stats - View detailed statistics about your server",
                    "🧹 /clear [amount] - Clean up chat by deleting messages (1-100, requires Manage Messages permission)",
                ],
                "footer": "🔐 Some commands require special permissions to prevent misuse",
            },
            "help": {
                "title": "💡 Help System",
                "description": "🗺️ Your guide to navigating all the bot's features! Never feel lost with our comprehensive help system.",
                "commands": [
                    "❓ /help - Show this interactive help menu with easy dropdown navigation"
                ],
                "footer": "🚀 The best way to discover everything this bot can do for your server!",
            },
        }

    def create_embed(self, category: str = "overview") -> discord.Embed:
        category_data = self.categories[category]

        embed = discord.Embed(
            title=category_data["title"],
            description=category_data["description"],
            color=EMBED_COLOR,
        )

        commands_text = "\n".join(category_data["commands"])
        embed.add_field(name="Available Commands", value=commands_text, inline=False)

        if "footer" in category_data:
            embed.set_footer(text=category_data["footer"])

        return embed

    @app_commands.command(
        name="help", description="❓ Show help menu with all available commands"
    )
    async def help_command(self, interaction: discord.Interaction):
        """Display an interactive help menu with command categories"""
        embed = self.create_embed()

        view = HelpView(self.create_embed)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
