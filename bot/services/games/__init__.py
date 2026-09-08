from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from random import shuffle
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from bot.cogs.minigames import MinigamesCog

logger = logging.getLogger(__name__)


def _suppress_discord() -> contextlib.AbstractContextManager[None]:
    return contextlib.suppress(discord.HTTPException, discord.NotFound)


class Game(ABC):
    def __init__(
        self,
        cog: MinigamesCog,
        players: list[discord.Member],
        timeout: float,
    ) -> None:
        self.cog = cog
        self.players = players
        self.timeout = timeout
        self._current_player_index = 0

        self.thread: discord.Thread | None = None
        self.message: discord.Message | None = None
        self.interaction: discord.Interaction | None = None
        self.view: discord.ui.View | None = None
        self.lock = asyncio.Lock()
        self.game_over = False

    @property
    def current_player(self) -> discord.Member:
        return self.players[self._current_player_index]

    def set_starting_player(self, player: discord.Member) -> None:
        self._current_player_index = self.players.index(player)

    def next_turn(self) -> None:
        self._current_player_index = (self._current_player_index + 1) % len(self.players)

    def assign_roles(self, roles: tuple[Any, ...]) -> dict[discord.Member, Any]:
        if len(self.players) != len(roles):
            raise ValueError(f"Expected {len(self.players)} roles, got {len(roles)}")
        shuffled = list(self.players)
        shuffle(shuffled)
        self.set_starting_player(shuffled[0])
        return dict(zip(shuffled, roles))

    async def start(self, interaction: discord.Interaction) -> None:
        channel = interaction.channel
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            raise RuntimeError("Cannot start a game without a text channel")

        thread = await channel.create_thread(
            name=f"{interaction.user.display_name}'s Game",
            type=discord.ChannelType.private_thread,
            invitable=False,
        )
        for player in self.players:
            await thread.add_user(player)

        self.thread = thread
        self.interaction = interaction
        self.cog.register_game(thread.id, self)

        mentions = ", ".join(player.mention for player in self.players)
        await interaction.response.send_message(
            f"Game started at {thread.mention} for {mentions}"
        )
        await self.send_board()

    async def finish(self, result_embed: discord.Embed) -> None:
        channel = self.interaction.channel if self.interaction else None
        if channel is not None:
            with _suppress_discord():
                await channel.send(embed=result_embed)
        await self.end_game()

    async def end_game(self) -> None:
        if self.game_over:
            return
        self.game_over = True

        if self.view:
            self.view.stop()

        if self.thread is not None:
            self.cog.unregister_game(self.thread.id)
            with _suppress_discord():
                await self.thread.delete()

        if self.interaction is not None:
            with _suppress_discord():
                await self.interaction.delete_original_response()

    async def handle_timeout(self) -> None:
        if self.game_over:
            return
        embed = discord.Embed(
            title="⏰ Game Timed Out",
            description="The game ended due to inactivity.",
            color=discord.Color.orange(),
        )
        if self.thread:
            with _suppress_discord():
                await self.thread.send(embed=embed)
        await self.end_game()

    async def check_turn(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.current_player:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return False
        return True

    async def check_membership(self, interaction: discord.Interaction) -> bool:
        if interaction.user not in self.players:
            await interaction.response.send_message(
                "You are not a player in this game.", ephemeral=True
            )
            return False
        return True

    @abstractmethod
    async def send_board(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_game_over(self) -> bool:
        raise NotImplementedError
