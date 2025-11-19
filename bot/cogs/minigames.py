from typing import TYPE_CHECKING, Dict, List, Union

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs import BaseCog, channel_allowed
from bot.services.minigames.chess import Chess
from bot.services.minigames.connect_four import Connect4
from bot.services.minigames.tic_tac_toe import TicTacToe

if TYPE_CHECKING:
    from bot.services.minigames import Game

    from . import MyBot


# ========= MINIGAMES COG ==========
class MinigamesCog(BaseCog, commands.GroupCog, name="minigames"):
    """Commands for playing fun minigames like Tic-Tac-Toe."""

    def __init__(self, bot: "MyBot"):
        super().__init__(bot)
        self.active_games: Dict[int, "Game"] = {}
        self.bot = bot
        self.logger = bot.logger.getChild("minigames")

    # ========== UNLOADER ==========
    async def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        for game in list(self.active_games.values()):
            await game.end_game()

    async def validate_game_start(
        self,
        interaction: discord.Interaction,
        opponents: Union[discord.Member, List[discord.Member]],
        allow_against_bot=False,
    ) -> bool:
        """Check if a game can be started."""
        if interaction.channel.id in self.active_games:
            await interaction.response.send_message(
                "There's already an active game in this channel!", ephemeral=True
            )
            return False

        opponents_list = (
            [opponents] if isinstance(opponents, discord.Member) else opponents
        )
        all_players = [interaction.user] + opponents_list

        # Check for self-play
        if interaction.user in opponents_list:
            await interaction.response.send_message(
                "You cannot play against yourself!", ephemeral=True
            )
            return False

        # Check for bots
        for player in all_players:
            if player.bot:
                if not allow_against_bot:
                    await interaction.response.send_message(
                        "You cannot play against bots in this game!", ephemeral=True
                    )
                    return False
                if player != self.bot:
                    await interaction.response.send_message(
                        "Only specific game bots are allowed!"
                    )
                    return False

        return True

    # ========== TIC TAC TOE ==========
    @app_commands.command(
        name="tic-tac-toe", description="❌⭕ Start a game of Tic-Tac-Toe"
    )
    @channel_allowed(__file__)
    async def tic_tac_toe(
        self, interaction: discord.Interaction, opponent: discord.Member
    ):
        if not await self.validate_game_start(interaction, opponent):
            return

        game = TicTacToe(self, [interaction.user, opponent])
        await game.start(interaction)

    # ========== CHESS ==========
    @app_commands.command(name="chess", description="♟️ Start a game of Chess")
    @channel_allowed(__file__)
    async def chess(self, interaction: discord.Interaction, opponent: discord.Member):
        if not await self.validate_game_start(interaction, opponent):
            return

        game = Chess(self, [interaction.user, opponent])
        await game.start(interaction)

    # ========== CONNECT 4 ==========
    @app_commands.command(
        name="connect4", description="🔴🔴🔴🔴 Start a game of Connect Four"
    )
    @channel_allowed(__file__)
    async def connect4(
        self, interaction: discord.Interaction, opponent: discord.Member
    ):
        if not await self.validate_game_start(interaction, opponent):
            return

        game = Connect4(self, [interaction.user, opponent])
        await game.start(interaction)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MinigamesCog(bot))
