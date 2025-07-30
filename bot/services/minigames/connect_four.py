from typing import TYPE_CHECKING, Dict, List, Optional

import discord

if TYPE_CHECKING:
    from bot.cogs.minigames import MinigamesCog

from . import EMBED_COLOR, Game

EMPTY_CELL = "⚫"
SYMBOLS = ("🔴", "🟡")
TIMEOUT_SECONDS = 60 * 5  # 5 minutes
ROWS = 6
COLS = 7


class Connect4Button(discord.ui.Button["Connect4View"]):
    """A button representing a column in the Connect 4 board."""

    def __init__(self, col: int):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=str(col + 1),
        )
        self.col = col

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.view.game.make_move(interaction, self.col)


class Connect4View(discord.ui.View):
    """The interactive view for the Connect 4 board."""

    def __init__(self, game: "Connect4"):
        super().__init__(timeout=game.timeout)
        self.game = game
        self._add_column_buttons()

    def _add_column_buttons(self) -> None:
        """Add column buttons to the view."""
        for col in range(COLS):
            button = Connect4Button(col)
            self.add_item(button)

    def update_buttons(self) -> None:
        """Update button states based on column availability."""
        for item in self.children:
            if isinstance(item, Connect4Button):
                item.disabled = (
                    self.game.is_column_full(item.col) or self.game.is_game_over()
                )

    async def on_timeout(self) -> None:
        await self.game.handle_timeout()


class Connect4(Game):
    """Connect 4 game implementation."""

    def __init__(
        self,
        cog: "MinigamesCog",
        players: List[discord.Member],
        timeout: int = TIMEOUT_SECONDS,
        **kwargs,
    ):
        if len(players) != 2:
            raise ValueError("Connect 4 requires exactly 2 players.")
        super().__init__(cog, players, timeout, **kwargs)
        self.symbols: Dict[discord.Member, str] = self.assign_roles(SYMBOLS)
        self.board = [[EMPTY_CELL for _ in range(COLS)] for _ in range(ROWS)]
        self.view: Connect4View

    async def start(self, interaction: discord.Interaction) -> None:
        """Start the game and send the initial board."""
        await super().start(interaction)
        self.view = Connect4View(self)
        embed = self._create_embed()
        self.message = await self.thread.send(embed=embed, view=self.view)

    async def make_move(self, interaction: discord.Interaction, col: int) -> None:
        """Process a player's move and update the game state."""
        async with self.lock:
            if not await self._validate_move(interaction, col):
                return

            await interaction.response.defer()

            # Find the lowest available row in the column
            row = self._get_drop_row(col)
            self.board[row][col] = self.symbols[self.current_player]

            winner = self.get_winner()
            game_over = self.is_game_over()

            if self.view:
                self.view.update_buttons()

            if game_over:
                embed = self._create_result_embed(winner)
                await self.interaction.channel.send(embed=embed)
                await self.end_game()
                return

            self.next_turn()
            embed = self._create_embed()
            await self.message.edit(embed=embed, view=self.view)

    async def _validate_move(self, interaction: discord.Interaction, col: int) -> bool:
        """Check if the move is valid and send error messages if not."""
        if not await self.check_membership(interaction):
            return False
        if not await self.check_turn(interaction):
            return False
        if self.is_column_full(col):
            await interaction.response.send_message(
                "That column is full!", ephemeral=True
            )
            return False
        if self.is_game_over():
            await interaction.response.send_message(
                "The game is already over.", ephemeral=True
            )
            return False
        return True

    def _get_drop_row(self, col: int) -> int:
        """Get the row where a piece would drop in the given column."""
        for row in range(ROWS - 1, -1, -1):
            if self.board[row][col] == EMPTY_CELL:
                return row
        return -1  # Column is full

    def is_column_full(self, col: int) -> bool:
        """Check if a column is full."""
        return self.board[0][col] != EMPTY_CELL

    def _create_embed(self) -> discord.Embed:
        """Create an embed showing the current game state."""
        player0, player1 = list(self.symbols.keys())
        embed = discord.Embed(title="Connect 4", color=EMBED_COLOR)
        embed.description = (
            f"{player0.mention} is {self.symbols[player0]}\n"
            f"{player1.mention} is {self.symbols[player1]}\n"
        )
        embed.add_field(name="Board", value=self._get_board_string())
        embed.add_field(
            name="Turn",
            value=f"{self.current_player.mention} ({self.symbols[self.current_player]})",
            inline=False,
        )
        return embed

    def _get_board_string(self) -> str:
        """Return a string representation of the board."""
        board_str = ""
        # Add column numbers
        board_str += "".join(f"{i+1}️⃣" for i in range(COLS)) + "\n"
        # Add board rows
        for row in self.board:
            board_str += "".join(row) + "\n"
        return board_str

    def _create_result_embed(self, winner: Optional[discord.Member]) -> discord.Embed:
        """Create an embed showing the final game result."""
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

        embed.add_field(
            name="Final Board", value=self._get_board_string(), inline=False
        )
        return embed

    def get_winner(self) -> Optional[discord.Member]:
        """Return the winner if there is one, else None."""
        # Check all possible winning positions
        for row in range(ROWS):
            for col in range(COLS):
                if self.board[row][col] == EMPTY_CELL:
                    continue

                symbol = self.board[row][col]
                player = next(p for p, s in self.symbols.items() if s == symbol)

                # Check horizontal
                if col <= COLS - 4:
                    if all(self.board[row][col + i] == symbol for i in range(4)):
                        return player

                # Check vertical
                if row <= ROWS - 4:
                    if all(self.board[row + i][col] == symbol for i in range(4)):
                        return player

                # Check diagonal (top-left to bottom-right)
                if row <= ROWS - 4 and col <= COLS - 4:
                    if all(self.board[row + i][col + i] == symbol for i in range(4)):
                        return player

                # Check diagonal (top-right to bottom-left)
                if row <= ROWS - 4 and col >= 3:
                    if all(self.board[row + i][col - i] == symbol for i in range(4)):
                        return player

        return None

    def is_game_over(self) -> bool:
        """Return True if the game is over (win or draw)."""
        if self.get_winner():
            return True
        # Check if board is full (draw)
        return all(self.board[0][col] != EMPTY_CELL for col in range(COLS))
