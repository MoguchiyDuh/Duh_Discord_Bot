from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs import BaseCog, channel_allowed
from bot.services.games.chess import Chess
from bot.services.games.connect_four import Connect4
from bot.services.games.tic_tac_toe import TicTacToe

if TYPE_CHECKING:
    from bot.core.bot import DuhBot
    from bot.services.games import Game

logger = logging.getLogger(__name__)


class MinigamesCog(BaseCog, commands.GroupCog, name="minigames"):
    """🎮 Chess, tic-tac-toe & connect four in private threads"""

    def __init__(self, bot: DuhBot) -> None:
        super().__init__(bot)
        self.active_games: dict[int, Game] = {}

    def register_game(self, thread_id: int, game: Game) -> None:
        self.active_games[thread_id] = game

    def unregister_game(self, thread_id: int) -> None:
        self.active_games.pop(thread_id, None)

    async def cog_unload(self) -> None:
        for game in list(self.active_games.values()):
            await game.end_game()

    async def validate_start(
        self,
        interaction: discord.Interaction,
        opponent: discord.Member,
    ) -> bool:
        if opponent.bot:
            await interaction.response.send_message(
                "You cannot play against bots!", ephemeral=True
            )
            return False
        if opponent == interaction.user:
            await interaction.response.send_message(
                "You cannot play against yourself!", ephemeral=True
            )
            return False
        return True

    @app_commands.command(name="tic-tac-toe", description="❌⭕ Start a game of Tic-Tac-Toe")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def tic_tac_toe(
        self, interaction: discord.Interaction, opponent: discord.Member
    ) -> None:
        if not await self.validate_start(interaction, opponent):
            return
        game = TicTacToe(self, [interaction.user, opponent])
        await game.start(interaction)

    @app_commands.command(name="chess", description="♟️ Start a game of Chess")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def chess(
        self, interaction: discord.Interaction, opponent: discord.Member
    ) -> None:
        if not await self.validate_start(interaction, opponent):
            return
        game = Chess(self, [interaction.user, opponent])
        await game.start(interaction)

    @app_commands.command(name="connect4", description="🔴🟡 Start a game of Connect Four")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def connect4(
        self, interaction: discord.Interaction, opponent: discord.Member
    ) -> None:
        if not await self.validate_start(interaction, opponent):
            return
        game = Connect4(self, [interaction.user, opponent])
        await game.start(interaction)


async def setup(bot: DuhBot) -> None:
    await bot.add_cog(MinigamesCog(bot))
