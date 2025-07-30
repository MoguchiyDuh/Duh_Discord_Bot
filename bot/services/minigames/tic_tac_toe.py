from typing import TYPE_CHECKING, Dict, List, Optional

import discord

if TYPE_CHECKING:
    from bot.cogs.minigames import MinigamesCog

from . import EMBED_COLOR, Game

EMPTY_CELL = "⬜"
SYMBOLS = ("❌", "⭕")
TIMEOUT_SECONDS = 60 * 3  # 3 minutes


class TicTacToeButton(discord.ui.Button["TicTacToeView"]):
    """A button representing a cell in the Tic-Tac-Toe board."""

    def __init__(self, row: int, col: int, symbol: str):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=symbol,
            row=row,
            disabled=symbol != EMPTY_CELL,
        )
        self.row = row
        self.col = col

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.game.make_move(interaction, self.row, self.col)


class TicTacToeView(discord.ui.View):
    """The interactive view for the Tic-Tac-Toe board."""

    def __init__(self, game: "TicTacToe"):
        super().__init__(timeout=game.timeout)
        self.game = game
        self.update_board()

    def update_board(self) -> None:
        """Refresh the view to match the current board state."""
        self.clear_items()
        for row in range(3):
            for col in range(3):
                button = TicTacToeButton(row, col, self.game.board[row][col])
                self.add_item(button)

    async def on_timeout(self) -> None:
        await self.game.handle_timeout()


class TicTacToe(Game):
    """Tic-Tac-Toe game implementation."""

    WINNING_COMBINATIONS = [
        # Rows
        [(0, 0), (0, 1), (0, 2)],
        [(1, 0), (1, 1), (1, 2)],
        [(2, 0), (2, 1), (2, 2)],
        # Columns
        [(0, 0), (1, 0), (2, 0)],
        [(0, 1), (1, 1), (2, 1)],
        [(0, 2), (1, 2), (2, 2)],
        # Diagonals
        [(0, 0), (1, 1), (2, 2)],
        [(0, 2), (1, 1), (2, 0)],
    ]

    def __init__(
        self,
        cog: "MinigamesCog",
        players: List[discord.Member],
        timeout: int = TIMEOUT_SECONDS,
        **kwargs,
    ):
        if len(players) != 2:
            raise ValueError("Tic-Tac-Toe requires exactly 2 players.")
        super().__init__(cog, players, timeout, **kwargs)
        self.symbols: Dict[discord.Member, str] = self.assign_roles(SYMBOLS)
        self.board = [[EMPTY_CELL for _ in range(3)] for _ in range(3)]
        self.view: Optional[TicTacToeView] = None

    async def start(self, interaction: discord.Interaction) -> None:
        """Start the game and send the initial board."""
        await super().start(interaction)
        self.view = TicTacToeView(self)
        embed = self._create_embed()
        self.message = await self.thread.send(embed=embed, view=self.view)

    async def make_move(
        self, interaction: discord.Interaction, row: int, col: int
    ) -> None:
        """Process a player's move and update the game state."""
        async with self.lock:
            if not await self._validate_move(interaction, row, col):
                return

            await interaction.response.defer()
            self.board[row][col] = self.symbols[self.current_player]

            winner = self.get_winner()
            game_over = self.is_game_over()

            self.view.update_board()

            if game_over:
                embed = self._create_result_embed(winner)
                await self.interaction.channel.send(embed=embed)
                await self.end_game()
                return

            self.next_turn()
            embed = self._create_embed()
            await self.message.edit(embed=embed, view=self.view)

    async def _validate_move(
        self, interaction: discord.Interaction, row: int, col: int
    ) -> bool:
        """Check if the move is valid and send error messages if not."""
        if not await self.check_membership(interaction):
            return False
        if not await self.check_turn(interaction):
            return False
        if self.board[row][col] != EMPTY_CELL:
            await interaction.response.send_message(
                "That space is already taken!", ephemeral=True
            )
            return False
        if self.is_game_over():
            await interaction.response.send_message(
                "The game is already over.", ephemeral=True
            )
            return False
        return True

    def _create_embed(self) -> discord.Embed:
        """Create an embed showing the current game state."""
        player0, player1 = list(self.symbols.keys())
        embed = discord.Embed(title="Tic-Tac-Toe", color=EMBED_COLOR)
        embed.description = (
            f"{player0.mention} is {self.symbols[player0]}\n"
            f"{player1.mention} is {self.symbols[player1]}\n"
        )
        embed.add_field(name="Board", value=self._get_board_string(), inline=False)
        embed.add_field(
            name="Turn",
            value=f"{self.current_player.mention} ({self.symbols[self.current_player]})",
            inline=False,
        )
        return embed

    def _get_board_string(self) -> str:
        """Return a string representation of the board."""
        return "\n".join(" ".join(row) for row in self.board)

    def _create_result_embed(self, winner: Optional[discord.Member]) -> discord.Embed:
        """Create an embed showing the final game result."""
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
        embed.add_field(
            name="Final Board", value=self._get_board_string(), inline=False
        )

        return embed

    def get_winner(self) -> Optional[discord.Member]:
        """Return the winner if there is one, else None."""
        for combo in self.WINNING_COMBINATIONS:
            symbols = [self.board[r][c] for r, c in combo]
            for player, symbol in self.symbols.items():
                if all(s == symbol for s in symbols):
                    return player
        return None

    def is_game_over(self) -> bool:
        """Return True if the game is over (win or draw)."""
        return bool(self.get_winner()) or all(
            cell != EMPTY_CELL for row in self.board for cell in row
        )
