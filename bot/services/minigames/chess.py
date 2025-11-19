import asyncio
from io import BytesIO
from typing import TYPE_CHECKING, Dict, List, Optional

import cairosvg
import chess
import chess.svg
import discord

from bot.cogs import EMBED_COLOR

from . import Game

if TYPE_CHECKING:
    from bot.cogs.minigames import MinigamesCog

TIMEOUT_SECONDS = 60 * 10  # 10 minutes
BOARD_FILENAME = "chess_board.png"
COLOR_NAMES = {chess.WHITE: "White", chess.BLACK: "Black"}


class ChessMoveModal(discord.ui.Modal, title="Make Your Chess Move"):
    def __init__(self, view: "ChessView"):
        super().__init__(timeout=view.game.timeout)
        self.view = view
        self.move_input = discord.ui.TextInput(
            label="Enter your move (e.g. e2e4, Nf3, O-O)",
            placeholder="Algebraic or UCI notation",
            required=True,
            min_length=2,
            max_length=10,
        )
        self.add_item(self.move_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.view.game.make_move(interaction, self.move_input.value)


class ChessView(discord.ui.View):
    def __init__(self, game: "Chess"):
        super().__init__(timeout=game.timeout)
        self.game = game

    async def validate_interaction(self, interaction: discord.Interaction) -> bool:
        return await self.game.check_turn(
            interaction
        ) and await self.game.check_membership(interaction)

    @discord.ui.button(label="Make Move", style=discord.ButtonStyle.primary)
    async def make_move(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if await self.validate_interaction(interaction):
            await interaction.response.send_modal(ChessMoveModal(self))

    @discord.ui.button(label="Resign", style=discord.ButtonStyle.danger)
    async def resign(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if await self.validate_interaction(interaction):
            await self.game.handle_resignation(interaction)

    @discord.ui.button(label="Draw", style=discord.ButtonStyle.secondary)
    async def offer_draw(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if await self.game.check_membership(interaction):
            await self.game.handle_draw_offer(interaction)

    async def on_timeout(self) -> None:
        await self.game.handle_timeout()


class Chess(Game):
    """A robust Discord chess game implementation."""

    def __init__(
        self,
        cog: "MinigamesCog",
        players: List[discord.Member],
        timeout: int = TIMEOUT_SECONDS,
        **kwargs,
    ):
        if len(players) != 2:
            raise ValueError("Chess requires exactly 2 players.")
        super().__init__(cog, players, timeout, **kwargs)
        self.board = chess.Board()
        self.colors: Dict[discord.Member, chess.Color] = self.assign_roles(
            COLOR_NAMES.keys()
        )
        self.draw_offered: Optional[discord.Member] = None
        self.resigned: Optional[discord.Member] = None
        self.view: ChessView

    @property
    def white(self) -> discord.Member:
        return next(p for p, c in self.colors.items() if c == chess.WHITE)

    @property
    def black(self) -> discord.Member:
        return next(p for p, c in self.colors.items() if c == chess.BLACK)

    @property
    def current_color(self) -> chess.Color:
        return self.board.turn

    @property
    def current_player(self) -> discord.Member:
        return self.white if self.current_color == chess.WHITE else self.black

    async def start(self, interaction: discord.Interaction) -> None:
        """Initialize and start the game."""
        await super().start(interaction)
        self.view = ChessView(self)
        embed = self._create_status_embed()
        file = await self._render_board()
        embed.set_image(url=f"attachment://{BOARD_FILENAME}")
        self.message = await self.thread.send(embed=embed, view=self.view, file=file)

    async def make_move(self, interaction: discord.Interaction, move_str: str) -> None:
        """Process a player's move and update game state."""
        async with self.lock:
            if not await self.check_turn(
                interaction
            ) or not await self.check_membership(interaction):
                return

            move = self._parse_move(move_str)
            if not move or not self.board.is_legal(move):
                await interaction.response.send_message(
                    "❌ Invalid or illegal move.", ephemeral=True
                )
                return

            await interaction.response.defer()
            self.board.push(move)
            self.draw_offered = None

            if self.is_game_over():
                await self.handle_game_end()
            else:
                embed = self._create_status_embed()
                file = await self._render_board()
                embed.set_image(url=f"attachment://{BOARD_FILENAME}")
                await self.message.edit(embed=embed, attachments=[file])

    def get_winner(self) -> Optional[discord.Member]:
        if self.resigned:
            return next(p for p in self.players if p != self.resigned)
        if self.board.is_checkmate():
            losing_color = not self.board.turn
            return next(p for p, c in self.colors.items() if c != losing_color)
        return None

    def is_game_over(self) -> bool:
        return self.board.is_game_over() or self.resigned

    def _parse_move(self, move_str: str) -> Optional[chess.Move]:
        for parser in [self.board.parse_san, self.board.parse_uci]:
            try:
                return parser(move_str.strip())
            except ValueError:
                continue
        return None

    async def _render_board(self) -> discord.File:
        """Render the chess board as a PNG file (runs SVG conversion in thread pool)."""
        orientation = self.colors[self.current_player]
        svg = chess.svg.board(
            board=self.board,
            orientation=orientation,
            lastmove=self.board.peek() if self.board.move_stack else None,
            check=self.board.king(self.board.turn) if self.board.is_check() else None,
        )
        # Run blocking cairosvg operation in thread pool
        png = await asyncio.to_thread(cairosvg.svg2png, bytestring=svg.encode("utf-8"))
        return discord.File(BytesIO(png), filename=BOARD_FILENAME)

    def _create_status_embed(self) -> discord.Embed:
        player0, player1 = list(self.colors.keys())
        embed = discord.Embed(title="Chess", color=EMBED_COLOR)
        embed.description = (
            f"{player0.mention} is {COLOR_NAMES[self.colors[player0]]}\n"
            f"{player1.mention} is {COLOR_NAMES[self.colors[player1]]}\n\n"
        )
        embed.add_field(
            name="Turn",
            value=f"{self.current_player.mention} ({COLOR_NAMES[self.colors[self.current_player]]})",
            inline=False,
        )
        if self.draw_offered:
            embed.description += f"\n⚖️ {self.draw_offered.mention} has offered a draw."
        if self.board.is_check():
            embed.description += (
                f"\n⚠️ {COLOR_NAMES[self.colors[self.current_player]]} is in check."
            )
        return embed

    def _create_result_embed(self) -> discord.Embed:
        embed = discord.Embed(title="Chess")
        if self.resigned:
            winner = self.get_winner()
            embed.description = (
                f"{self.resigned.mention} resigned.\n🎉 {winner.mention} wins!"
            )
            embed.color = discord.Color.teal()
        elif self.board.is_checkmate():
            winner = self.get_winner()
            embed.description = f"🎉 {winner.mention} wins by checkmate!"
            embed.color = discord.Color.gold()
        elif self.board.is_stalemate():
            embed.description = "Draw by stalemate."
            embed.color = discord.Color.light_grey()
        elif self.board.is_insufficient_material():
            embed.description = "Draw due to insufficient material."
            embed.color = discord.Color.light_grey()
        elif self.board.is_seventyfive_moves():
            embed.description = "Draw by 75-move rule."
            embed.color = discord.Color.light_grey()
        elif self.board.is_fivefold_repetition():
            embed.description = "Draw by repetition."
            embed.color = discord.Color.light_grey()
        else:
            embed.description = "🤝 Draw accepted."
            embed.color = discord.Color.light_grey()
        embed.add_field(name="Move Log", value=self._get_move_log(), inline=False)
        return embed

    async def handle_game_end(self) -> None:
        embed = self._create_result_embed()
        file = await self._render_board()
        embed.set_image(url=f"attachment://{BOARD_FILENAME}")
        await self.interaction.channel.send(embed=embed, file=file)
        await self.end_game()

    async def _update_board_state(self) -> None:
        """Update the board message with current state."""
        embed = self._create_status_embed()
        file = await self._render_board()
        embed.set_image(url=f"attachment://{BOARD_FILENAME}")
        await self.message.edit(embed=embed, attachments=[file])

    def _get_move_log(self) -> str:
        moves = [move.uci() for move in self.board.move_stack]
        return f"```{' '.join(moves) if moves else 'No moves.'}```"

    async def handle_resignation(self, interaction: discord.Interaction) -> None:
        async with self.lock:
            if self.resigned:
                await interaction.response.send_message(
                    "A player has already resigned.", ephemeral=True
                )
                return
            self.resigned = interaction.user
            await interaction.response.defer()
            await self.handle_game_end()

    async def handle_draw_offer(self, interaction: discord.Interaction) -> None:
        async with self.lock:
            if self.draw_offered and self.draw_offered != interaction.user:
                # Accept draw
                await interaction.response.defer()
                await self.handle_game_end()
            elif self.draw_offered == interaction.user:
                await interaction.response.send_message(
                    "❌ You already offered a draw.", ephemeral=True
                )
            else:
                # Offer draw
                self.draw_offered = interaction.user
                await interaction.response.send_message(
                    "⚖️ Draw offer sent. Waiting for the other player to accept.",
                    ephemeral=True,
                )
                await self._update_board_state()
