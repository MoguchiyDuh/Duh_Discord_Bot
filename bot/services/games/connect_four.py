from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from bot.cogs import EMBED_COLOR
from bot.services.games import Game

if TYPE_CHECKING:
    from bot.cogs.minigames import MinigamesCog

EMPTY_CELL = "⚫"
SYMBOLS = ("🔴", "🟡")
TIMEOUT_SECONDS = 60.0 * 5
ROWS = 6
COLS = 7


class Connect4(Game):
    def __init__(
        self, cog: MinigamesCog, players: list[discord.Member]
    ) -> None:
        super().__init__(cog, players, TIMEOUT_SECONDS)
        self.symbols: dict[discord.Member, str] = self.assign_roles(SYMBOLS)
        self.board = [[EMPTY_CELL for _ in range(COLS)] for _ in range(ROWS)]

    async def send_board(self) -> None:
        self.view = Connect4View(self)
        if self.thread:
            self.message = await self.thread.send(
                embed=self._board_embed(), view=self.view
            )

    async def make_move(self, interaction: discord.Interaction, col: int) -> None:
        async with self.lock:
            if not await self._validate(interaction, col):
                return

            await interaction.response.defer()
            row = self._drop_row(col)
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

    async def _validate(self, interaction: discord.Interaction, col: int) -> bool:
        if not await self.check_membership(interaction):
            return False
        if not await self.check_turn(interaction):
            return False
        if self.is_game_over():
            await interaction.response.send_message(
                "The game is already over.", ephemeral=True
            )
            return False
        if self.is_column_full(col):
            await interaction.response.send_message("That column is full!", ephemeral=True)
            return False
        return True

    def _drop_row(self, col: int) -> int:
        for row in range(ROWS - 1, -1, -1):
            if self.board[row][col] == EMPTY_CELL:
                return row
        raise ValueError(f"Column {col} is full")

    def is_column_full(self, col: int) -> bool:
        return self.board[0][col] != EMPTY_CELL

    def get_winner(self) -> discord.Member | None:
        symbol_to_player = {symbol: player for player, symbol in self.symbols.items()}
        directions = ((0, 1), (1, 0), (1, 1), (1, -1))
        for row in range(ROWS):
            for col in range(COLS):
                symbol = self.board[row][col]
                if symbol == EMPTY_CELL:
                    continue
                for d_row, d_col in directions:
                    end_row, end_col = row + 3 * d_row, col + 3 * d_col
                    if not (0 <= end_row < ROWS and 0 <= end_col < COLS):
                        continue
                    if all(
                        self.board[row + i * d_row][col + i * d_col] == symbol
                        for i in range(4)
                    ):
                        return symbol_to_player[symbol]
        return None

    def is_game_over(self) -> bool:
        return self.get_winner() is not None or all(
            self.is_column_full(col) for col in range(COLS)
        )

    def _board_embed(self) -> discord.Embed:
        (player0, symbol0), (player1, symbol1) = self.symbols.items()
        embed = discord.Embed(title="Connect 4", color=EMBED_COLOR)
        embed.description = f"{player0.mention} is {symbol0}\n{player1.mention} is {symbol1}\n"
        embed.add_field(name="Board", value=self._board_string(), inline=False)
        embed.add_field(
            name="Turn",
            value=f"{self.current_player.mention} ({self.symbols[self.current_player]})",
            inline=False,
        )
        return embed

    def _board_string(self) -> str:
        numbers = "".join(f"{keycap(i)}️⃣" for i in range(1, COLS + 1))
        rows = "\n".join("".join(row) for row in self.board)
        return f"{numbers}\n{rows}"

    def _result_embed(self, winner: discord.Member | None) -> discord.Embed:
        embed = discord.Embed(title="Connect 4")
        if winner:
            embed.add_field(
                name="Winner",
                value=f"🎉 {winner.mention} ({self.symbols[winner]}) wins!",
                inline=False,
            )
            embed.color = discord.Color.gold()
        else:
            embed.add_field(name="Result", value="🤝 It's a draw!", inline=False)
            embed.color = discord.Color.light_grey()
        embed.add_field(name="Final Board", value=self._board_string(), inline=False)
        return embed


def keycap(digit: int) -> str:
    return f"{digit}\ufe0f\u20e3"


class Connect4Button(discord.ui.Button["Connect4View"]):
    def __init__(self, col: int) -> None:
        super().__init__(label=str(col + 1), style=discord.ButtonStyle.secondary)
        self.col = col

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view:
            await self.view.game.make_move(interaction, self.col)


class Connect4View(discord.ui.View):
    def __init__(self, game: Connect4) -> None:
        super().__init__(timeout=game.timeout)
        self.game = game
        for col in range(COLS):
            self.add_item(Connect4Button(col))

    def refresh(self) -> None:
        for item in self.children:
            if isinstance(item, Connect4Button):
                item.disabled = (
                    self.game.is_column_full(item.col) or self.game.is_game_over()
                )

    async def on_timeout(self) -> None:
        await self.game.handle_timeout()
