import asyncio
import os
from abc import ABC, abstractmethod
from random import shuffle
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import discord

from bot.cogs import EMBED_COLOR

if TYPE_CHECKING:
    from bot.cogs.minigames import MinigamesCog


class Game(ABC):
    """
    Abstract base class for implementing multiplayer games in Discord.
    Designed for games like Chess, Tic Tac Toe, Connect 4, Mafia, etc.
    """

    def __init__(
        self,
        cog: "MinigamesCog",
        players: List[discord.Member],
        timeout: int = 60 * 3,
        **game_config: Any,
    ) -> None:
        if not players:
            raise ValueError("At least one player is required")
        if timeout <= 0:
            raise ValueError("Timeout must be positive")

        self.cog = cog
        self.players: List[discord.Member] = players
        self._current_player_index: int = 0

        self.thread: Optional[discord.Thread] = None
        self.message: Optional[discord.Message] = None
        self.interaction: Optional[discord.Interaction] = None
        self.view: Optional[discord.ui.View] = None

        self.timeout: int = timeout
        self.config: Dict[str, Any] = game_config
        self.lock: asyncio.Lock = asyncio.Lock()
        self.game_over: bool = False

    @property
    def current_player(self) -> discord.Member:
        """Returns the player whose turn it is currently."""
        return self.players[self._current_player_index]

    @property
    def current_player_index(self) -> int:
        """Returns the current player index."""
        return self._current_player_index

    def set_starting_player(self, player: discord.Member) -> None:
        """Set which player goes first."""
        if player not in self.players:
            raise ValueError("Player not in game")
        self._current_player_index = self.players.index(player)

    def assign_roles(self, roles: Tuple) -> Dict[discord.Member, Any]:
        """
        Assign roles to players randomly and return a mapping of players to roles.
        Useful for games like Mafia.
        """
        if len(self.players) != len(roles):
            raise ValueError(f"Expected {len(self.players)} roles, got {len(roles)}")
        # Convert to list to ensure we can shuffle and copy
        shuffled_players = list(self.players)
        shuffle(shuffled_players)
        self.set_starting_player(shuffled_players[0])
        return dict(zip(shuffled_players, roles))

    @abstractmethod
    async def start(self, interaction: discord.Interaction) -> None:
        """Initialize and start the game."""
        thread = await interaction.channel.create_thread(
            name=f"{interaction.user.display_name}'s Game",
            type=discord.ChannelType.private_thread,
            invitable=False,
        )
        for player in self.players:
            await thread.add_user(player)
        self.thread = thread
        self.cog.active_games[interaction.guild_id] = self
        await interaction.response.send_message(
            f"Game started at {thread.mention} for {', '.join([player.mention for player in self.players])}"
        )
        self.interaction = interaction

    @abstractmethod
    async def make_move(
        self, interaction: discord.Interaction, *args: Any, **kwargs: Any
    ) -> None:
        """
        Process a player's move and update game state.
        Should validate the move, update state, and advance the turn if valid.
        """
        raise NotImplementedError

    @abstractmethod
    def get_winner(self) -> Optional[Union[discord.Member, List[discord.Member]]]:
        """
        Return the winner(s) of the game, or None if there is no winner yet or a draw.
        """
        raise NotImplementedError

    @abstractmethod
    def is_game_over(self) -> bool:
        """
        Return True if the game has ended (win, draw, or other terminal state).
        """
        raise NotImplementedError

    async def check_turn(self, interaction: discord.Interaction) -> bool:
        """
        Verify if the interacting user is the current player.
        Returns True if it is their turn, otherwise sends an ephemeral message and returns False.
        """
        if interaction.user != self.current_player:
            await interaction.response.send_message(
                "It's not your turn!", ephemeral=True
            )
            return False
        return True

    async def check_membership(self, interaction: discord.Interaction) -> bool:
        """
        Verify if the interacting user is a player in this game.
        Returns True if they are, otherwise sends an ephemeral message and returns False.
        """
        if interaction.user not in self.players:
            await interaction.response.send_message(
                "You are not a player in this game.", ephemeral=True
            )
            return False
        return True

    async def end_game(self) -> None:
        """
        Clean up game resources and declare results.
        Removes the game from active games and stops the view.
        """
        if self.game_over:
            return

        try:
            self.game_over = True

            if self.view and not self.view.is_finished():
                self.view.stop()

            await self.thread.delete()
            await self.interaction.delete_original_response()

            del self.cog.active_games[self.interaction.guild_id]
        except Exception as e:
            pass

    def next_turn(self) -> None:
        """Advance the game to the next player's turn."""
        self._current_player_index = (self._current_player_index + 1) % len(
            self.players
        )

    async def handle_timeout(self) -> None:
        """
        Handle game timeout by cleaning up and notifying players.
        """
        if self.game_over:
            return

        embed = discord.Embed(
            title=f"⏰ {self.__class__.__name__} Timed Out",
            description="The game ended due to inactivity.",
            color=discord.Color.orange(),
        )

        if self.message:
            try:
                # await self.message.edit(embed=embed, view=None)
                await self.interaction.followup.send(embed=embed)
            except discord.HTTPException:
                pass

        await self.end_game()

    def _is_image_filename(self, text: Optional[str]) -> bool:
        """
        Check if the input string appears to be a filename with a valid image extension.
        """
        if not text or " " in text or "." not in text:
            return False
        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        _, ext = os.path.splitext(text.lower())
        return ext in image_extensions
