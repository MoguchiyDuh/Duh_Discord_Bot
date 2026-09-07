from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from bot.cogs import EMBED_COLOR
from bot.services.games import Game

if TYPE_CHECKING:
    from bot.cogs.minigames import MinigamesCog

EMPTY_CELL = "⬜"
SYMBOLS = ("❌", "⭕")
TIMEOUT_SECONDS = 60.0 * 3

WINNING_COMBINATIONS = [
    *[[(r, c) for c in range(3)] for r in range(3)],
    *[[(r, c) for r in range(3)] for c in range(3)],
    [(0, 0), (1, 1), (2, 2)],
    [(0, 2), (1, 1), (2, 0)],
]


class TicTacToe(Game):
    def __init__(
        self, cog: MinigamesCog, players: list[discord.Member]
    ) -> None:
        super().__init__(cog, players, TIMEOUT_SECONDS)
        self.symbols: dict[discord.Member, str] = self.assign_roles(SYMBOLS)
        self.board = [[EMPTY_CELL for _ in range(3)] for _ in range(3)]

    async def send_board(self) -> None:
        self.view = TicTacToeView(self)
        embed = self._board_embed()
        if self.thread:
            self.message = await self.thread.send(embed=embed, view=self.view)

    async def make_move(self, interaction: discord.Interaction, row: int, col: int) -> None:
        async with self.lock:
            if not await self._validate(interaction, row, col):
                return

            await interaction.response.defer()
            self.board[row][col] = self.symbols[self.current_player]

            winner = self.get_winner()
            if self.is_game_over():
                if self.view:
                    self.view.stop()
                await self.finish(self._result_embed(winner))
                return

            self.next_turn()
            if self.view:
                self.view.refresh()
            if self.message:
                await self.message.edit(embed=self._board_embed(), view=self.view)

    async def _validate(
        self, interaction: discord.Interaction, row: int, col: int
    ) -> bool:
        if not await self.check_membership(interaction):
            return False
        if not await self.check_turn(interaction):
            return False
        if self.is_game_over():
            await interaction.response.send_message(
                "The game is already over.", ephemeral=True
            )
            return False
        if self.board[row][col] != EMPTY_CELL:
            await interaction.response.send_message(
                "That space is already taken!", ephemeral=True
            )
            return False
        return True

    def get_winner(self) -> discord.Member | None:
        for combo in WINNING_COMBINATIONS:
            line = [self.board[r][c] for r, c in combo]
            for player, symbol in self.symbols.items():
                if all(cell == symbol for cell in line):
                    return player
        return None

    def is_game_over(self) -> bool:
        return self.get_winner() is not None or all(
            cell != EMPTY_CELL for row in self.board for cell in row
        )

    def _board_embed(self) -> discord.Embed:
        (player0, symbol0), (player1, symbol1) = self.symbols.items()
        embed = discord.Embed(title="Tic-Tac-Toe", color=EMBED_COLOR)
        embed.description = f"{player0.mention} is {symbol0}\n{player1.mention} is {symbol1}\n"
        embed.add_field(name="Board", value=self._board_string(), inline=False)
        embed.add_field(
            name="Turn",
            value=f"{self.current_player.mention} ({self.symbols[self.current_player]})",
            inline=False,
        )
        return embed

    def _board_string(self) -> str:
        return "\n".join(" ".join(row) for row in self.board)

    def _result_embed(self, winner: discord.Member | None) -> discord.Embed:
        embed = discord.Embed(title="Tic-Tac-Toe")
        if winner:
            embed.add_field(
                name="Winner",
                value=f"🎉 {winner.mention} ({self.symbols[winner]}) wins!",
                inline=False,
            )
            embed.color = discord.Color.gold()
        else:
            embed.description = "🤝 It's a draw!"
            embed.color = discord.Color.light_grey()
        embed.add_field(name="Final Board", value=self._board_string(), inline=False)
        return embed


class TicTacToeButton(discord.ui.Button["TicTacToeView"]):
    def __init__(self, row: int, col: int, symbol: str) -> None:
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=symbol,
            row=row,
            disabled=symbol != EMPTY_CELL,
        )
        self.row = row
        self.col = col

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view:
            await self.view.game.make_move(interaction, self.row, self.col)


class TicTacToeView(discord.ui.View):
    def __init__(self, game: TicTacToe) -> None:
        super().__init__(timeout=game.timeout)
        self.game = game
        self.refresh()

    def refresh(self) -> None:
        self.clear_items()
        for row in range(3):
            for col in range(3):
                self.add_item(TicTacToeButton(row, col, self.game.board[row][col]))

    async def on_timeout(self) -> None:
        await self.game.handle_timeout()
