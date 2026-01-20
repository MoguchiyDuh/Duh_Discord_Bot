import asyncio
from dataclasses import dataclass, field
from enum import Enum, auto
from random import shuffle
from typing import TYPE_CHECKING, Dict, List, Optional, Set

import discord
from discord import app_commands, ui
from discord.ext import commands

from bot.services.get_lyrics import get_lyrics
from bot.services.yt_source import Track, TrackFetcher

if TYPE_CHECKING:
    from . import MyBot

from bot.utils.config import MAX_QUEUE_LENGTH

from . import DISCORD_FFMPEG_OPTIONS, EMBED_COLOR, BaseCog, channel_allowed


# ========== MUSIC CLASS ==========
class PlayerState(Enum):
    """Enum for player states."""

    IDLE = auto()
    PLAYING = auto()
    PAUSED = auto()
    STOPPED = auto()


@dataclass
class MusicPlayer:
    """Abstract base class for a media player managing playback state and queue."""

    voice_client: Optional[discord.VoiceClient] = None
    current_item: Optional[Track] = None
    queue: List[Track] = field(default_factory=list)
    state: PlayerState = PlayerState.IDLE
    loop: bool = False

    @property
    def is_active(self) -> bool:
        """Check if the player is currently playing or paused."""
        return self.state in (PlayerState.PLAYING, PlayerState.PAUSED)

    def clear(self) -> None:
        """Clear the queue and reset state."""
        self.queue.clear()
        self.current_item = None
        self.state = PlayerState.IDLE
        self.loop = False

    def shuffle_queue(self) -> None:
        """Shuffle the current queue."""
        shuffle(self.queue)

    def skip_current(self) -> Optional[Track]:
        """Skip the currently playing track."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
        return self.current_item

    def skip_index(self, index: int) -> List[Track]:
        """
        Skip a specific track.
        Index 0 = current track, 1 = first in queue, etc.
        """
        if index == 0:
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()
                return [self.current_item] if self.current_item else []
            return []
        elif 1 <= index <= len(self.queue):
            idx = index - 1
            skipped = [self.queue[idx]]
            del self.queue[idx]
            return skipped
        return []

    def skip_range(self, start: int, end: int) -> List[Track]:
        """
        Skip a range of tracks.
        0 = current track, 1 = first in queue, etc.
        Inclusive of both start and end.
        """
        skipped = []

        if start > end or start < 0:
            return []

        if start == 0:
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()
                if self.current_item:
                    skipped.append(self.current_item)
            start = 1
            end = max(end, 1)

        start_idx = start - 1
        end_idx = min(end - 1, len(self.queue) - 1)

        if start_idx <= end_idx and start_idx < len(self.queue):
            skipped.extend(self.queue[start_idx : end_idx + 1])
            del self.queue[start_idx : end_idx + 1]

        return skipped


# ========== VIEW ==========
class TrackSelectionView(ui.View):
    """Interactive view for selecting tracks from search results."""

    def __init__(self, cog: "MusicCog", search_results: Dict[str, str], user_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.selected_track: Optional[str] = None
        self.user_id = user_id
        self._add_buttons(search_results)

    def _add_buttons(self, search_results: Dict[str, str]) -> None:
        """Add selection buttons for each track."""
        for idx, (title, url) in enumerate(search_results.items(), start=1):
            btn = ui.Button(
                label=str(idx),
                style=discord.ButtonStyle.primary,
                custom_id=url,
                row=(0 if idx <= 3 else 1),
            )
            btn.callback = self._create_callback(url)
            self.add_item(btn)

        # Add control buttons
        cancel_btn = ui.Button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
        cancel_btn.callback = self._create_callback("cancel")
        self.add_item(cancel_btn)

    def _create_callback(self, url: str):
        """Factory method for button callbacks."""

        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message(
                    "You didn't initiate this search!", ephemeral=True
                )
                return

            self.selected_track = url
            await self.cleanup(interaction)

        return callback

    async def cleanup(self, interaction: Optional[discord.Interaction] = None) -> None:
        """Safely remove the view and delete the message"""
        try:
            self.stop()
            if interaction:
                await interaction.message.delete()
        except Exception as e:
            self.cog.logger.error(f"Error during view cleanup: {e}", exc_info=True)

    async def on_timeout(self) -> None:
        """Disable all buttons when the view times out."""
        await self.cleanup()


class PlaylistSelectionModal(ui.Modal, title="Select Playlist Range"):
    """Modal for entering custom playlist selection."""

    selection = ui.TextInput(
        label="Enter selection",
        placeholder="e.g., '1' or '1-5' or '1,3,5' or '1-3,7,10-12'",
        max_length=100,
    )

    def __init__(self, view: "PlaylistSelectionView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.view.selection = self.selection.value
        await interaction.response.defer()
        await self.view.cleanup(interaction)


class PlaylistSelectionView(ui.View):
    """Interactive view for selecting which tracks to add from a playlist."""

    def __init__(self, cog: "MusicCog", user_id: int, track_count: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.selection: Optional[str] = None
        self.user_id = user_id
        self.track_count = track_count

    @ui.button(label="Add All", style=discord.ButtonStyle.success, row=0)
    async def add_all(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You didn't initiate this request!", ephemeral=True
            )
            return
        self.selection = "all"
        await self.cleanup(interaction)

    @ui.button(label="Custom Selection", style=discord.ButtonStyle.primary, row=0)
    async def custom_selection(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You didn't initiate this request!", ephemeral=True
            )
            return
        modal = PlaylistSelectionModal(self)
        await interaction.response.send_modal(modal)

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=0)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You didn't initiate this request!", ephemeral=True
            )
            return
        self.selection = "cancel"
        await self.cleanup(interaction)

    async def cleanup(self, interaction: Optional[discord.Interaction] = None) -> None:
        """Safely remove the view and delete the message"""
        try:
            self.stop()
            if interaction and interaction.message:
                await interaction.message.delete()
        except Exception as e:
            self.cog.logger.error(f"Error during view cleanup: {e}", exc_info=True)

    async def on_timeout(self) -> None:
        """Disable all buttons when the view times out."""
        self.selection = "cancel"
        await self.cleanup()


# ========== MUSIC COG ==========
class MusicCog(BaseCog, commands.GroupCog, name="music"):
    """Music commands for playing, managing, and controlling audio playback."""

    def __init__(self, bot: "MyBot"):
        super().__init__(bot)
        self.bot = bot
        self.players: Dict[int, MusicPlayer] = {}
        self.logger = bot.logger.getChild("music")

    # ========== UNLOADER ==========
    async def cog_unload(self) -> None:
        """Clean up resources when the cog is unloaded."""
        for player in list(self.players.values()):
            if player.voice_client:
                await player.voice_client.disconnect()
        self.players.clear()

    # ========== LISTENERS ==========
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice state changes including auto-disconnect."""
        if member == self.bot.user:
            return

        player = self.players.get(member.guild.id)
        if not player or not player.voice_client:
            return

        # Auto-disconnect if bot is alone in voice channel
        if len(player.voice_client.channel.members) == 1:
            await self._cleanup_player(member.guild)
            self.logger.info(
                f"Auto-disconnected from {member.guild.name} due to inactivity"
            )

    # ========== HELPERS ==========
    async def _cleanup_player(self, guild: discord.Guild) -> None:
        """Clean up player resources for a guild with proper error handling."""
        player = self.players.get(guild.id)
        if player:
            try:
                if player.voice_client:
                    if player.voice_client.is_playing():
                        player.voice_client.stop()
                    await asyncio.wait_for(
                        player.voice_client.disconnect(), timeout=5.0
                    )
            except asyncio.TimeoutError:
                self.logger.warning(f"Voice disconnect timeout in {guild.name}")
            except Exception as e:
                self.logger.error(f"Error during voice cleanup in {guild.name}: {e}")
            finally:
                player.clear()
                del self.players[guild.id]

    async def _ensure_voice(
        self, interaction: discord.Interaction
    ) -> Optional[MusicPlayer]:
        """Ensure the bot is in a voice channel with the user."""
        if not interaction.user.voice:
            await interaction.response.send_message(
                "🔊 You must be in a voice channel to use this command.", ephemeral=True
            )
            return None

        if interaction.guild.id not in self.players:
            self.players[interaction.guild.id] = MusicPlayer()

        player = self.players[interaction.guild.id]

        if not player.voice_client:
            player.voice_client = await interaction.user.voice.channel.connect()
            self.logger.info(
                f"Joined voice channel {interaction.user.voice.channel.name} "
                f"in guild {interaction.guild.name}"
            )
        elif player.voice_client.channel != interaction.user.voice.channel:
            await player.voice_client.move_to(interaction.user.voice.channel)

        return player

    # ========== JOIN ==========
    @app_commands.command(name="join", description="➕ Joins your voice channel.")
    @channel_allowed(__file__)
    async def join(self, interaction: discord.Interaction) -> None:
        """Join the user's voice channel."""
        self.logger.debug(f"User @{interaction.user.name} invoked /join")
        player = await self._ensure_voice(interaction)
        if player:
            await interaction.response.send_message(
                f"✅ Joined {player.voice_client.channel.name}"
            )

    # ========== LEAVE ==========
    @app_commands.command(
        name="leave", description="🚪 Leaves the voice channel and clears the queue."
    )
    @channel_allowed(__file__)
    async def leave(self, interaction: discord.Interaction) -> None:
        """Leave the voice channel and clean up."""
        self.logger.debug(f"User @{interaction.user.name} invoked /leave")
        player = self.players.get(interaction.guild.id)
        if not player or not player.voice_client:
            await interaction.response.send_message(
                "📴 I'm not in a voice channel.", ephemeral=True
            )
            return

        await self._cleanup_player(interaction.guild)
        await interaction.response.send_message("✅ Left the voice channel.")

    # ========== PLAY ==========
    @app_commands.command(
        name="play",
        description="▶️ Play music from YouTube, SoundCloud. Supports URLs, playlists, or search queries.",
    )
    @app_commands.describe(query="YouTube URL, playlist URL, or search query")
    @channel_allowed(__file__)
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        """Play music from various sources."""

        # Input validation
        query = query.strip()
        if not query:
            await interaction.response.send_message(
                "❌ Query cannot be empty.", ephemeral=True
            )
            return
        if len(query) > 500:
            await interaction.response.send_message(
                "❌ Query too long (max 500 characters).", ephemeral=True
            )
            return

        self.logger.debug(
            f"User @{interaction.user.name} invoked /play with query: {query}"
        )
        player = await self._ensure_voice(interaction)
        if not player:
            return

        await interaction.response.defer()

        if len(player.queue) >= MAX_QUEUE_LENGTH:
            self.logger.warning("Queue is full")
            await interaction.followup.send(
                f"📛 Queue is full! Limit {MAX_QUEUE_LENGTH}.",
                ephemeral=True,
            )
            return

        try:
            if query.startswith(("http://", "https://")):
                if "list=" in query:  # Playlist
                    self.logger.debug("Init playlist fetching")
                    await self._handle_playlist(interaction, player, query)
                else:  # Single track
                    self.logger.debug("Init url track fetching")
                    success = await self._add_track_to_queue(interaction, player, query)
                    if success and not player.is_active:
                        await self._play_next(interaction)
            else:  # Search query
                self.logger.debug("Init yt track search")
                await self._handle_search(interaction, player, query)

        except Exception as e:
            self.logger.error(f"Error in play command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while processing your request.", ephemeral=True
            )

    def _parse_selection(self, selection: str, max_count: int) -> Set[int]:
        """Parse user selection string into set of indices (1-based)."""
        indices = set()

        try:
            parts = selection.replace(" ", "").split(",")
            for part in parts:
                if "-" in part:
                    # Range: "1-5"
                    start, end = map(int, part.split("-", 1))
                    if start < 1 or end > max_count or start > end:
                        continue
                    indices.update(range(start, end + 1))
                else:
                    # Single: "3"
                    idx = int(part)
                    if 1 <= idx <= max_count:
                        indices.add(idx)
        except ValueError:
            self.logger.error(f"Invalid selection format: {selection}")

        return indices

    async def _handle_playlist(
        self, interaction: discord.Interaction, player: MusicPlayer, playlist_url: str
    ) -> None:
        """Handle playlist URL with track selection."""
        # Collect all track URLs first
        track_urls = []
        try:
            async for track_url in TrackFetcher.fetch_playlist(playlist_url):
                track_urls.append(track_url)
        except Exception as e:
            self.logger.error(f"Failed to fetch playlist: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to fetch playlist.", ephemeral=True
            )
            return

        if not track_urls:
            await interaction.followup.send(
                "ℹ️ Playlist is empty or unavailable.", ephemeral=True
            )
            return

        # Show selection view
        embed = discord.Embed(
            title="📜 Playlist Selection",
            description=f"Found {len(track_urls)} tracks in playlist.\n\nSelect which tracks to add:",
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="Options",
            value="• **Add All** - Add all tracks\n• **Custom Selection** - Choose specific tracks or ranges",
            inline=False,
        )
        embed.set_footer(text="Selection will timeout in 60 seconds")

        view = PlaylistSelectionView(self, interaction.user.id, len(track_urls))
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()

        if not view.selection or view.selection == "cancel":
            return

        # Determine which tracks to add
        if view.selection == "all":
            indices_to_add = set(range(1, len(track_urls) + 1))
        else:
            indices_to_add = self._parse_selection(view.selection, len(track_urls))
            if not indices_to_add:
                await interaction.followup.send(
                    "❌ Invalid selection format.", ephemeral=True
                )
                return

        # Add selected tracks
        track_count = 0
        first_track = True
        failed_tracks = 0

        for idx in sorted(indices_to_add):
            if len(player.queue) >= MAX_QUEUE_LENGTH:
                self.logger.warning("Queue is full")
                await interaction.followup.send(
                    f"⚠️ Queue full! Added {track_count} tracks, skipped {len(indices_to_add) - track_count}."
                )
                return

            try:
                track_url = track_urls[idx - 1]  # Convert to 0-based
                success = await self._add_track_to_queue(
                    interaction, player, track_url, notify=False
                )
                if success:
                    track_count += 1
                    if first_track and not player.is_active:
                        first_track = False
                        await self._play_next(interaction)
                else:
                    failed_tracks += 1
            except Exception as e:
                self.logger.error(f"Error adding track {idx}: {e}")
                failed_tracks += 1
                continue

        if track_count > 0:
            status_msg = f"✅ Added {track_count} track(s) from playlist"
            if failed_tracks > 0:
                status_msg += f" ({failed_tracks} failed)"
            await interaction.followup.send(status_msg)
        else:
            await interaction.followup.send(
                "❌ No tracks could be added from playlist.", ephemeral=True
            )

    async def _handle_search(
        self, interaction: discord.Interaction, player: MusicPlayer, search_query: str
    ) -> None:
        """Handle search query."""
        search_results = await TrackFetcher.fetch_track_by_name(search_query)
        if not search_results:
            await interaction.followup.send(
                "🔍 No results found for your query.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🔍 Search Results",
            description="Select a track to play:",
            color=EMBED_COLOR,
        )
        for idx, title in enumerate(search_results.keys(), start=1):
            embed.add_field(name=f"{idx}. {title[:50]}", value="\u200b", inline=False)
        embed.set_footer(text="Selection will timeout in 60 seconds")

        view = TrackSelectionView(self, search_results, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()

        if not view.selected_track or view.selected_track == "cancel":
            return

        success = await self._add_track_to_queue(
            interaction, player, view.selected_track
        )
        if success and not player.is_active:
            await self._play_next(interaction)

    async def _add_track_to_queue(
        self,
        interaction: discord.Interaction,
        player: MusicPlayer,
        track_url: str,
        notify: bool = True,
    ) -> bool:
        """Add a track to the queue"""
        track = await TrackFetcher.fetch_track_by_url(track_url)
        if track:
            player.queue.append(track)
            self.logger.info(f"Added track to queue: {track.title}")
            if notify:
                await interaction.followup.send(f"➕ Added to queue: {track.title}")
            return True
        else:
            self.logger.error(f"Failed to fetch track: {track_url}")
            if notify:
                await interaction.followup.send(
                    "❌ Could not fetch the track.", ephemeral=True
                )
            return False

    async def _play_next(self, interaction: discord.Interaction) -> None:
        """Play the next track in the queue."""
        self.logger.debug("Playing the next track")
        guild = interaction.guild
        player = self.players.get(guild.id)
        if not player or not player.voice_client:
            return

        if player.loop and player.current_item:
            self.logger.debug("Looping the current track")
            player.queue.insert(0, player.current_item)

        if not player.queue:
            self.logger.debug("No tracks in the queue, idling")
            player.state = PlayerState.IDLE
            player.current_item = None
            return

        player.current_item = player.queue.pop(0)

        try:
            async with asyncio.timeout(30):
                source = await discord.FFmpegOpusAudio.from_probe(
                    player.current_item.audio_url,
                    **DISCORD_FFMPEG_OPTIONS,
                )

            player.voice_client.play(
                source,
                after=lambda e: self._handle_playback_complete(interaction, e),
            )
            player.state = PlayerState.PLAYING
            self.logger.debug(
                f"Started streaming the track {player.current_item.title}"
            )

            embed = self._create_now_playing_embed(player)
            await interaction.channel.send(embed=embed)

        except asyncio.TimeoutError:
            self.logger.error(
                f"Timeout creating audio source for {player.current_item.title}"
            )
            await interaction.followup.send("Stream creation timeout, skipping track.")
            await self._play_next(interaction)

        except Exception as e:
            self.logger.error(f"Playback error: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ Error occurred while playing the track."
            )
            await self._play_next(interaction)

    def _handle_playback_complete(
        self,
        interaction: discord.Interaction,
        error: Optional[Exception],
    ) -> None:
        """Handle completion of audio playback."""
        if error:
            self.logger.error(
                f"Playback error in guild {interaction.guild.id}: {error}"
            )

        # Schedule the next track in the event loop
        asyncio.run_coroutine_threadsafe(self._play_next(interaction), self.bot.loop)

    # ========== SKIP ==========
    @app_commands.command(name="skip", description="⏭️ Skip tracks by index or range.")
    @app_commands.describe(
        query="Index or range to skip (e.g. '1', '0' current track, '1-3')"
    )
    @channel_allowed(__file__)
    async def skip(
        self, interaction: discord.Interaction, query: Optional[str] = None
    ) -> None:
        """Skip the current track, a specific track, or a range of tracks."""
        self.logger.debug(
            f"User @{interaction.user.name} invoked /skip with query: {query}"
        )

        player = self.players.get(interaction.guild.id)
        if not player or not player.is_active:
            await interaction.response.send_message(
                "🔇 I'm not playing anything.", ephemeral=True
            )
            return

        skipped_tracks = []
        if not query:
            # Skip current track
            track = player.skip_current()
            if track:
                skipped_tracks.append(track)
            self.logger.debug(f"Skipped current track")
        else:
            try:
                if "-" in query:
                    # Range skip
                    parts = query.split("-")
                    if len(parts) == 2:
                        start, end = map(int, parts)
                        if start > end:
                            await interaction.response.send_message(
                                "❌ Invalid range: start cannot be greater than end.",
                                ephemeral=True,
                            )
                            return
                        skipped_tracks = player.skip_range(start, end)
                    else:
                        await interaction.response.send_message(
                            "❌ Invalid range format. Use format like '1-3'.",
                            ephemeral=True,
                        )
                        return
                else:
                    # Single index skip
                    index = int(query)
                    skipped_tracks = player.skip_index(index)
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid number format. Use integers like '0' or ranges like '1-3'.",
                    ephemeral=True,
                )
                return

        if not skipped_tracks:
            self.logger.debug("No tracks were skipped.")
            await interaction.response.send_message(
                "ℹ️ No tracks were skipped.", ephemeral=True
            )
            return

        skipped_titles = [track.title for track in skipped_tracks if track]
        await interaction.response.send_message(
            f"⏭ Skipped {len(skipped_tracks)} track(s)"
        )
        self.logger.info(f"Skipped: {', '.join(skipped_titles)}")

    # ========== SHOW THE QUEUE ==========
    @app_commands.command(name="queue", description="📜 Show the current queue.")
    @channel_allowed(__file__)
    async def queue(self, interaction: discord.Interaction) -> None:
        """Display the current queue."""
        self.logger.debug(f"User @{interaction.user.name} invoked /queue")
        player = self.players.get(interaction.guild.id)
        if not player or not player.queue:
            await interaction.response.send_message("ℹ️ The queue is empty.")
            return

        queue_list = "\n".join(
            f"**{i+1}.** [{track.title[:50]}]({track.url})"
            for i, track in enumerate(player.queue[:10])  # Show first 10 tracks
        )

        embed = discord.Embed(
            title=f"📜 Queue ({len(player.queue)} tracks)",
            description=queue_list,
            color=EMBED_COLOR,
        )

        if player.current_item:
            embed.add_field(
                name="Now Playing",
                value=f"[{player.current_item.title}]({player.current_item.url})",
                inline=False,
            )

        if len(player.queue) > 10:
            embed.set_footer(text=f"... and {len(player.queue) - 10} more tracks")

        await interaction.response.send_message(embed=embed)

    def _create_now_playing_embed(self, player: MusicPlayer) -> discord.Embed:
        track = player.current_item
        queue = player.queue
        self.logger.debug(f"Now playing {track.title}")
        embed = discord.Embed(
            title="🎶 Now Playing",
            description=f"[{track.title}]({track.url})",
            color=EMBED_COLOR,
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        if track.author:
            embed.add_field(
                name="Author",
                value=(
                    f"[{track.author}]({track.author_url})"
                    if track.author_url
                    else track.author
                ),
                inline=True,
            )
        if track.duration:
            embed.add_field(
                name="Duration",
                value=track.formatted_duration,
                inline=True,
            )

        if queue:
            embed.add_field(
                name="Next Up",
                value=f"[{queue[0].title}]({queue[0].url})",
                inline=True,
            )
        return embed

    # ========== SHOW THE CURRENT TRACK ==========
    @app_commands.command(
        name="current", description="🎵 Show the currently playing track."
    )
    @channel_allowed(__file__)
    async def current(self, interaction: discord.Interaction) -> None:
        """Display the currently playing track."""
        self.logger.debug(f"User @{interaction.user.name} invoked /current")
        player = self.players.get(interaction.guild.id)
        if not player or not player.current_item:
            await interaction.response.send_message(
                "🔇 I'm not playing anything.", ephemeral=True
            )
            return

        embed = self._create_now_playing_embed(player)
        await interaction.response.send_message(embed=embed)

    # ========== PAUSE ==========
    @app_commands.command(name="pause", description="⏸️ Pause the current track.")
    @channel_allowed(__file__)
    async def pause(self, interaction: discord.Interaction) -> None:
        """Pause playback."""
        self.logger.debug(f"User @{interaction.user.name} invoked /pause")
        player = self.players.get(interaction.guild.id)
        if not player or not player.voice_client:
            self.logger.warning("Not playing anything")
            await interaction.response.send_message(
                "🔇 I'm not playing anything.", ephemeral=True
            )
            return

        if player.voice_client.is_playing():
            player.voice_client.pause()
            self.logger.info("Change state to PAUSED")
            player.state = PlayerState.PAUSED
            await interaction.response.send_message("⏸️ Playback paused.")
        else:
            self.logger.warning("Already paused")
            await interaction.response.send_message(
                "ℹ️ Playback is already paused.", ephemeral=True
            )

    # ========== RESUME ==========
    @app_commands.command(name="resume", description="▶️ Resume playback.")
    @channel_allowed(__file__)
    async def resume(self, interaction: discord.Interaction) -> None:
        """Resume playback."""
        self.logger.debug(f"User @{interaction.user.name} invoked /resume")
        player = self.players.get(interaction.guild.id)
        if not player or not player.voice_client:
            self.logger.warning("Not playing anything")
            await interaction.response.send_message(
                "🔇 I'm not playing anything.", ephemeral=True
            )
            return

        if player.voice_client.is_paused():
            player.voice_client.resume()
            self.logger.debug("Change state to PLAYING")
            player.state = PlayerState.PLAYING
            await interaction.response.send_message("▶️ Playback resumed.")
        else:
            self.logger.warning("Player is not paused")
            await interaction.response.send_message(
                "ℹ️ Playback is not paused.", ephemeral=True
            )

    # ========== TOGGLE LOOPING ==========
    @app_commands.command(
        name="loop", description="🔁 Toggle looping of the current track."
    )
    @channel_allowed(__file__)
    async def loop(self, interaction: discord.Interaction) -> None:
        """Toggle track looping."""
        self.logger.debug(f"User @{interaction.user.name} invoked /loop")
        player = self.players.get(interaction.guild.id)
        if not player or not player.current_item:
            self.logger.warning("Not playing anything")
            await interaction.response.send_message(
                "🔇 I'm not playing anything.", ephemeral=True
            )
            return

        player.loop = not player.loop
        self.logger.info(f"Looping {player.loop}")
        status = "enabled" if player.loop else "disabled"
        await interaction.response.send_message(f"🔁 Loop {status}.")

    # ========== SHUFFLE THE QUEUE ==========
    @app_commands.command(name="shuffle", description="🔀 Shuffle the current queue.")
    @channel_allowed(__file__)
    async def shuffle(self, interaction: discord.Interaction) -> None:
        self.logger.debug(f"User @{interaction.user.name} invoked /shuffle")
        player = self.players.get(interaction.guild.id)
        if not player or not player.queue:
            self.logger.warning("Queue is empty")
            await interaction.response.send_message(
                "ℹ️ The queue is empty, nothing to shuffle.", ephemeral=True
            )
            return

        player.shuffle_queue()
        self.logger.info("Queue is shuffled")
        await interaction.response.send_message("🔀 Queue is shuffled.")

    # ========== CLEAR THE QUEUE ==========
    @app_commands.command(name="clear", description="🧹 Clear the queue.")
    @channel_allowed(__file__)
    async def clear(self, interaction: discord.Interaction) -> None:
        """Clear the queue."""
        self.logger.debug(f"User @{interaction.user.name} invoked /clear (music)")
        player = self.players.get(interaction.guild.id)
        if not player or not player.queue:
            await interaction.response.send_message(
                "ℹ️ The queue is already empty.", ephemeral=True
            )
            return

        player.queue.clear()
        self.logger.info("Queue cleared")
        await interaction.response.send_message("🗑️ Queue cleared.")

    # ========== GET LYRICS ==========
    @app_commands.command(name="lyrics", description="📝 Get lyrics for a song.")
    @app_commands.describe(
        query="Song name to search lyrics for (default: current track)"
    )
    @channel_allowed(__file__)
    async def lyrics(
        self, interaction: discord.Interaction, query: Optional[str] = None
    ) -> None:
        """Fetch and display lyrics."""
        self.logger.debug(
            f"User @{interaction.user.name} invoked /lyrics with query {query}"
        )
        await interaction.response.defer()

        if not query:
            player = self.players.get(interaction.guild.id)
            if player and player.current_item:
                query = player.current_item.title
                self.logger.debug("Set the current track as a query")
            else:
                self.logger.warning("No track is playing")
                await interaction.followup.send(
                    "🔇 No track is playing and no query provided.", ephemeral=True
                )
                return

        try:
            parts = query.split(" - ", 1)
            name = parts[0]
            if len(parts) > 1:
                artist = parts[1]
            else:
                artist = None
            response = await get_lyrics(track_name=name, artist_name=artist)

            for i, chunk in enumerate(response.text):
                embed = discord.Embed(
                    title=f"🎵 {response.title}" if i == 0 else None,
                    description=chunk,
                    color=EMBED_COLOR,
                )
                await interaction.followup.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Failed to fetch lyrics: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to fetch lyrics", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(MusicCog(bot))
