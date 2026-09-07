from __future__ import annotations

import asyncio
import contextlib
import logging
from io import BytesIO
from typing import TYPE_CHECKING

import chess
import chess.svg
import discord

from bot.cogs import EMBED_COLOR
from bot.services.games import Game, _suppress_discord

if TYPE_CHECKING:
    import cairosvg

if TYPE_CHECKING:
    from bot.cogs.minigames import MinigamesCog

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60.0 * 10
BOARD_FILENAME = "chess_board.png"
COLOR_NAMES = {chess.WHITE: "White", chess.BLACK: "Black"}


class Chess(Game):
    def __init__(
        self, cog: MinigamesCog, players: list[discord.Member]
    ) -> None:
        super().__init__(cog, players, TIMEOUT_SECONDS)
        self.board = chess.Board()
        self.colors: dict[discord.Member, chess.Color] = self.assign_roles(
            (chess.WHITE, chess.BLACK)
        )
        self.draw_offered: discord.Member | None = None
        self.resigned: discord.Member | None = None

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

    async def send_board(self) -> None:
        self.view = ChessView(self)
        if self.thread is None:
            return
        file = await self._render_board()
        embed = self._status_embed()
        embed.set_image(url=f"attachment://{BOARD_FILENAME}")
        self.message = await self.thread.send(embed=embed, view=self.view, file=file)

    async def make_move(self, interaction: discord.Interaction, move_str: str) -> None:
        async with self.lock:
            if self.game_over:
                return
            if (
                not await self.check_turn(interaction)
                or not await self.check_membership(interaction)
            ):
                return

            move = self._parse_move(move_str)
            if move is None or not self.board.is_legal(move):
                await interaction.response.send_message(
                    "❌ Invalid or illegal move.", ephemeral=True
                )
                return

            await interaction.response.defer()
            self.board.push(move)
            self.draw_offered = None

            if self.is_game_over():
                await self._finish_game()
            else:
                await self._update_board()

    async def handle_resignation(self, interaction: discord.Interaction) -> None:
        async with self.lock:
            if self.game_over:
                return
            if self.resigned:
                await interaction.response.send_message(
                    "A player has already resigned.", ephemeral=True
                )
                return
            self.resigned = interaction.user
            await interaction.response.defer()
            await self._finish_game()

    async def handle_draw_offer(self, interaction: discord.Interaction) -> None:
        async with self.lock:
            if self.game_over:
                return
            if self.draw_offered and self.draw_offered != interaction.user:
                await interaction.response.defer()
                await self._finish_game(accepted=True)
            elif self.draw_offered == interaction.user:
                await interaction.response.send_message(
                    "❌ You already offered a draw.", ephemeral=True
                )
            else:
                self.draw_offered = interaction.user
                await interaction.response.send_message(
                    "⚖️ Draw offer sent. Waiting for the other player to accept.",
                    ephemeral=True,
                )
                await self._update_board()

    async def _finish_game(self, *, accepted: bool = False) -> None:
        if self.view:
            self.view.stop()
        embed = self._result_embed(accepted)
        file = await self._render_board()
        embed.set_image(url=f"attachment://{BOARD_FILENAME}")
        await self.finish_with_file(embed, file)

    async def finish_with_file(
        self, embed: discord.Embed, file: discord.File
    ) -> None:
        channel = self.interaction.channel if self.interaction else None
        if channel is not None:
            with _suppress_discord():
                await channel.send(embed=embed, file=file)
        await self.end_game()

    async def _update_board(self) -> None:
        if self.message is None:
            return
        file = await self._render_board()
        embed = self._status_embed()
        embed.set_image(url=f"attachment://{BOARD_FILENAME}")
        with contextlib.suppress(discord.HTTPException):
            await self.message.edit(
                embed=embed, view=self.view, attachments=[file]
            )

    def _parse_move(self, move_str: str) -> chess.Move | None:
        candidate = move_str.strip()
        for parser in (self.board.parse_san, self.board.parse_uci):
            try:
                return parser(candidate)
            except ValueError:
                continue
        return None

    async def _render_board(self) -> discord.File:
        import cairosvg

        orientation = self.colors[self.current_player]
        svg = chess.svg.board(
            board=self.board,
            orientation=orientation,
            lastmove=self.board.peek() if self.board.move_stack else None,
            check=self.board.king(self.board.turn) if self.board.is_check() else None,
        )
        png = await asyncio.to_thread(cairosvg.svg2png, bytestring=svg.encode("utf-8"))
        return discord.File(BytesIO(png), filename=BOARD_FILENAME)

    def get_winner(self) -> discord.Member | None:
        if self.resigned:
            return next(p for p in self.players if p != self.resigned)
        if self.board.is_checkmate():
            losing_color = self.board.turn
            return next(p for p, c in self.colors.items() if c != losing_color)
        return None

    def is_game_over(self) -> bool:
        return self.board.is_game_over() or self.resigned is not None

    def _status_embed(self) -> discord.Embed:
        (player0, color0), (player1, color1) = self.colors.items()
        embed = discord.Embed(title="Chess", color=EMBED_COLOR)
        embed.description = (
            f"{player0.mention} is {COLOR_NAMES[color0]}\n"
            f"{player1.mention} is {COLOR_NAMES[color1]}\n"
        )
        embed.add_field(
            name="Turn",
            value=f"{self.current_player.mention} ({COLOR_NAMES[self.current_color]})",
            inline=False,
        )
        if self.draw_offered:
            embed.description += f"\n⚖️ {self.draw_offered.mention} has offered a draw."
        if self.board.is_check():
            embed.description += (
                f"\n⚠️ {COLOR_NAMES[self.current_color]} is in check."
            )
        return embed

    def _result_embed(self, accepted: bool) -> discord.Embed:
        embed = discord.Embed(title="Chess")
        winner = self.get_winner()
        if self.resigned:
            embed.description = (
                f"{self.resigned.mention} resigned.\n🎉 {winner.mention} wins!"
            )
            embed.color = discord.Color.teal()
        elif winner:
            embed.description = f"🎉 {winner.mention} wins by checkmate!"
            embed.color = discord.Color.gold()
        elif accepted or self.draw_offered:
            embed.description = "🤝 Draw accepted."
            embed.color = discord.Color.light_grey()
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
            embed.description = "🤝 Draw."
            embed.color = discord.Color.light_grey()

        moves = [move.uci() for move in self.board.move_stack]
        move_log = " ".join(moves) if moves else "No moves."
        embed.add_field(name="Move Log", value=f"```{move_log}```", inline=False)
        return embed


class ChessMoveModal(discord.ui.Modal, title="Make Your Chess Move"):
    move_input = discord.ui.TextInput(
        label="Enter your move (e.g. e2e4, Nf3, O-O)",
        placeholder="Algebraic or UCI notation",
        required=True,
        min_length=2,
        max_length=10,
    )

    def __init__(self, view: ChessView) -> None:
        super().__init__()
        self.chess_view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.chess_view.game.make_move(interaction, self.move_input.value)


class ChessView(discord.ui.View):
    def __init__(self, game: Chess) -> None:
        super().__init__(timeout=game.timeout)
        self.game = game

    async def _validate(self, interaction: discord.Interaction) -> bool:
        return await self.game.check_turn(interaction) and await self.game.check_membership(
            interaction
        )

    @discord.ui.button(label="Make Move", style=discord.ButtonStyle.primary)
    async def make_move(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if await self._validate(interaction):
            await interaction.response.send_modal(ChessMoveModal(self))

    @discord.ui.button(label="Resign", style=discord.ButtonStyle.danger)
    async def resign(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await self._validate(interaction):
            await self.game.handle_resignation(interaction)

    @discord.ui.button(label="Draw", style=discord.ButtonStyle.secondary)
    async def offer_draw(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if await self.game.check_membership(interaction):
            await self.game.handle_draw_offer(interaction)

    async def on_timeout(self) -> None:
        await self.game.handle_timeout()
