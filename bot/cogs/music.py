import asyncio
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from bot.services.get_lyrics import get_lyrics
from bot.services.yt_source import Track, TrackFetcher
from bot.utils.logger import BASE_LOG_FILE_NAME, setup_logger

# Constants
DISCORD_FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -af aresample=async=1 -filter:a 'volume=0.3'",
}
MAX_QUEUE_LENGTH = 100
MAX_PLAYLIST_TRACKS = 50
EMBED_COLOR = discord.Color.blurple()

# Logger setup
logger = setup_logger(name="music", log_to_file=True, log_file=BASE_LOG_FILE_NAME)


class PlayerState(Enum):
    """Enum for player states."""

    IDLE = auto()
    PLAYING = auto()
    PAUSED = auto()
    STOPPED = auto()


@dataclass
class GuildPlayer:
    """Manages music playback for a single guild."""

    voice_client: Optional[discord.VoiceClient] = None
    queue: List[Track] = None
    current_track: Optional[Track] = None
    state: PlayerState = PlayerState.IDLE
    loop: bool = False

    def __post_init__(self):
        self.queue = []

    @property
    def is_active(self) -> bool:
        """Check if the player is active (playing or paused)."""
        return self.state in (PlayerState.PLAYING, PlayerState.PAUSED)

    def clear(self):
        """Reset the player to its initial state."""
        self.queue.clear()
        self.current_track = None
        self.state = PlayerState.IDLE
        self.loop = False

    def skip(self, count: int = 1) -> List[Track]:
        """Skip one or more tracks from the queue."""
        if count <= 0:
            return []

        skipped = []
        for _ in range(min(count, len(self.queue))):
            skipped.append(self.queue.pop(0))
        return skipped


class TrackSelectionView(ui.View):
    """Interactive view for selecting tracks from search results."""

    def __init__(self, search_results: Dict[str, str], user_id: int):
        super().__init__(timeout=60)
        self.selected_track: Optional[str] = None
        self.user_id = user_id
        self._add_buttons(search_results)

    def _add_buttons(self, search_results: Dict[str, str]):
        """Add selection buttons for each track."""
        for idx, (title, url) in enumerate(search_results.items(), start=1):
            btn = ui.Button(
                label=idx,
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

            await interaction.response.defer()
            self.selected_track = url
            await self.cleanup()

        return callback

    async def cleanup(self):
        """Safely remove the view and delete the message"""
        try:
            self.stop()
            for item in self.children:
                item.disabled = True

            if self.message:
                try:
                    await self.message.edit(view=self)  # Disable all buttons first
                except discord.NotFound:
                    pass
                except discord.HTTPException as e:
                    logger.warning(f"Failed to edit message during cleanup: {e}")

                try:
                    await self.message.delete()
                except discord.NotFound:
                    pass  # Message already deleted
                except discord.HTTPException as e:
                    logger.error(f"Failed to delete message: {e}")
        except Exception as e:
            logger.error(f"Error during view cleanup: {e}")

    async def on_timeout(self):
        """Disable all buttons when the view times out."""
        await self.cleanup()


class MusicCog(commands.GroupCog, name="music"):
    """Music commands for playing, managing, and controlling audio playback."""

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.players: Dict[int, GuildPlayer] = {}

    async def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        for player in self.players.values():
            if player.voice_client:
                await player.voice_client.disconnect()
        self.players.clear()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Handle voice state changes including auto-disconnect."""
        if member == self.bot.user:
            return

        player = self.players.get(member.guild.id)
        if not player or not player.voice_client:
            return

        # Auto-disconnect if bot is alone in voice channel
        if len(player.voice_client.channel.members) == 1:
            await self.cleanup_player(member.guild)
            logger.info(f"Auto-disconnected from {member.guild.name} due to inactivity")

    async def cleanup_player(self, guild: discord.Guild):
        """Clean up player resources for a guild."""
        player = self.players.get(guild.id)
        if player:
            if player.voice_client:
                await player.voice_client.disconnect()
            del self.players[guild.id]

    async def ensure_voice(
        self, interaction: discord.Interaction
    ) -> Optional[GuildPlayer]:
        """Ensure the bot is in a voice channel with the user."""
        if not interaction.user.voice:
            await interaction.response.send_message(
                "❌ You must be in a voice channel to use this command.", ephemeral=True
            )
            return None

        if interaction.guild.id not in self.players:
            self.players[interaction.guild.id] = GuildPlayer()

        player = self.players[interaction.guild.id]

        if not player.voice_client:
            player.voice_client = await interaction.user.voice.channel.connect()
            logger.info(
                f"Joined voice channel {interaction.user.voice.channel.name} "
                f"in guild {interaction.guild.name}"
            )
        elif player.voice_client.channel != interaction.user.voice.channel:
            await player.voice_client.move_to(interaction.user.voice.channel)

        return player

    @app_commands.command(name="join", description="Joins your voice channel.")
    async def join(self, interaction: discord.Interaction):
        """Join the user's voice channel."""
        player = await self.ensure_voice(interaction)
        if player:
            await interaction.response.send_message(
                f"✅ Joined {player.voice_client.channel.name}"
            )

    @app_commands.command(
        name="leave", description="Leaves the voice channel and clears the queue."
    )
    async def leave(self, interaction: discord.Interaction):
        """Leave the voice channel and clean up."""
        player = self.players.get(interaction.guild.id)
        if not player or not player.voice_client:
            await interaction.response.send_message(
                "❌ I'm not in a voice channel.", ephemeral=True
            )
            return

        await self.cleanup_player(interaction.guild)
        await interaction.response.send_message("✅ Left the voice channel.")

    @app_commands.command(
        name="play",
        description="Play music from YouTube. Supports URLs, playlists, or search queries.",
    )
    @app_commands.describe(query="YouTube URL, playlist URL, or search query")
    async def play(self, interaction: discord.Interaction, query: str):
        """Play music from various sources."""
        player = await self.ensure_voice(interaction)
        if not player:
            return

        await interaction.response.defer()

        try:
            if query.startswith(("http://", "https://")):
                if "list=" in query:  # Playlist
                    await self._handle_playlist(interaction, player, query)
                else:  # Single track
                    await self._handle_single_track(interaction, player, query)
            else:  # Search query
                await self._handle_search(interaction, player, query)

            if not player.is_active and player.queue:
                await self._play_next(interaction.guild)

        except Exception as e:
            logger.error(f"Error in play command: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while processing your request.", ephemeral=True
            )

    async def _handle_playlist(
        self, interaction: discord.Interaction, player: GuildPlayer, playlist_url: str
    ):
        """Handle playlist URL."""
        playlist_tracks = await TrackFetcher.fetch_playlist(playlist_url)
        if not playlist_tracks:
            await interaction.followup.send(
                "❌ Could not fetch playlist tracks.", ephemeral=True
            )
            return

        # Limit the number of tracks to prevent abuse
        tracks_to_add = list(playlist_tracks.values())[:MAX_PLAYLIST_TRACKS]
        tasks = [self._add_track_to_queue(player, url) for url in tracks_to_add]
        await asyncio.gather(*tasks)

        await interaction.followup.send(
            f"✅ Added {len(tracks_to_add)} tracks from playlist to queue."
        )

    async def _handle_single_track(
        self, interaction: discord.Interaction, player: GuildPlayer, track_url: str
    ):
        """Handle single track URL."""
        if len(player.queue) >= MAX_QUEUE_LENGTH:
            await interaction.followup.send(
                "❌ Queue is full! Please wait for current tracks to finish.",
                ephemeral=True,
            )
            return

        track = await self._add_track_to_queue(player, track_url)
        if not track:
            await interaction.followup.send(
                "❌ Could not fetch track information.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎵 Added to queue",
            description=f"[{track.title}]({track_url})",
            color=EMBED_COLOR,
        )
        embed.set_thumbnail(url=track.thumbnail)
        if track.uploader:
            embed.set_footer(text=f"Uploaded by {track.uploader}")
        await interaction.followup.send(embed=embed)

    async def _handle_search(
        self, interaction: discord.Interaction, player: GuildPlayer, search_query: str
    ):
        """Handle search query."""
        search_results = await TrackFetcher.fetch_track_by_name(search_query)
        if not search_results:
            await interaction.followup.send(
                "❌ No results found for your query.", ephemeral=True
            )
            return

        view = TrackSelectionView(search_results, interaction.user.id)
        message = await interaction.followup.send(
            embed=self._create_search_embed(search_results), view=view, ephemeral=True
        )
        view.message = message
        await view.wait()

        if not view.selected_track:
            return
        elif view.selected_track == "cancel":
            await view.cleanup()
            return

        await self._handle_single_track(interaction, player, view.selected_track)

    def _create_search_embed(self, search_results: Dict[str, str]) -> discord.Embed:
        """Create an embed for search results."""
        embed = discord.Embed(
            title="🔍 Search Results",
            description="Select a track to play:",
            color=EMBED_COLOR,
        )

        for idx, title in enumerate(search_results.keys(), start=1):
            embed.add_field(name=f"{idx}. {title[:50]}", value="\u200b", inline=False)

        embed.set_footer(text="Selection will timeout in 60 seconds")
        return embed

    async def _add_track_to_queue(
        self, player: GuildPlayer, url: str
    ) -> Optional[Track]:
        """Add a track to the queue and return the Track object."""
        track = await TrackFetcher.fetch_track_by_url(url)
        if track:
            player.queue.append(track)
            logger.info(f"Added track to queue: {track.title}")
        return track

    async def _play_next(self, guild: discord.Guild):
        """Play the next track in the queue."""
        player = self.players.get(guild.id)
        if not player or not player.voice_client:
            return

        if player.loop and player.current_track:
            player.queue.insert(0, player.current_track)

        if not player.queue:
            player.state = PlayerState.IDLE
            return

        player.current_track = player.queue.pop(0)
        player.state = PlayerState.PLAYING

        try:
            source = await asyncio.to_thread(
                discord.FFmpegPCMAudio,
                player.current_track.audio_url,
                **DISCORD_FFMPEG_OPTIONS,
            )

            player.voice_client.play(
                source, after=lambda e: self._handle_playback_complete(guild, e)
            )

            # Notify in the last channel that requested playback
            channel = player.voice_client.guild.system_channel
            if channel:
                embed = discord.Embed(
                    title="🎶 Now Playing",
                    description=f"[{player.current_track.title}]({player.current_track.url})",
                    color=EMBED_COLOR,
                )
                embed.set_thumbnail(url=player.current_track.thumbnail)
                if player.current_track.uploader:
                    embed.set_footer(
                        text=f"Uploaded by {player.current_track.uploader}"
                    )
                await channel.send(embed=embed)

        except Exception as e:
            logger.error(f"Playback error: {e}", exc_info=True)
            await self._play_next(guild)

    def _handle_playback_complete(
        self, guild: discord.Guild, error: Optional[Exception]
    ):
        """Handle completion of audio playback."""
        if error:
            logger.error(f"Playback error in guild {guild.id}: {error}")

        # Schedule the next track in the event loop
        asyncio.run_coroutine_threadsafe(self._play_next(guild), self.bot.loop)

    @app_commands.command(
        name="skip", description="Skip the current or specified tracks."
    )
    @app_commands.describe(amount="Number of tracks to skip (default: 1)")
    async def skip(self, interaction: discord.Interaction, amount: int = 1):
        """Skip tracks in the queue."""
        player = self.players.get(interaction.guild.id)
        if not player or not player.is_active:
            await interaction.response.send_message(
                "❌ Nothing is currently playing.", ephemeral=True
            )
            return

        if amount < 1:
            await interaction.response.send_message(
                "❌ Please specify a positive number.", ephemeral=True
            )
            return

        skipped_tracks = []
        if player.current_track:
            skipped_tracks.append(player.current_track.title)
            player.voice_client.stop()

        # Skip additional tracks from queue
        if amount > 1 and player.queue:
            skipped = player.skip(amount - 1)
            skipped_tracks.extend(t.title for t in skipped)

        message = f"⏭ Skipped {len(skipped_tracks)} track(s)"
        if len(skipped_tracks) <= 3:
            message += f": {', '.join(skipped_tracks)}"

        await interaction.response.send_message(message)

    @app_commands.command(name="queue", description="Show the current queue.")
    async def queue(self, interaction: discord.Interaction):
        """Display the current queue."""
        player = self.players.get(interaction.guild.id)
        if not player or not player.queue:
            await interaction.response.send_message(
                "ℹ️ The queue is empty.", ephemeral=True
            )
            return

        queue_list = "\n".join(
            f"**{i+1}.** [{track.title[:50]}]({track.url})"
            for i, track in enumerate(player.queue[:10])  # Show first 10 tracks
        )

        embed = discord.Embed(
            title=f"🎶 Queue ({len(player.queue)} tracks)",
            description=queue_list,
            color=EMBED_COLOR,
        )

        if player.current_track:
            embed.add_field(
                name="Now Playing",
                value=f"[{player.current_track.title}]({player.current_track.url})",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="now", description="Show the currently playing track.")
    async def now(self, interaction: discord.Interaction):
        """Display the currently playing track."""
        player = self.players.get(interaction.guild.id)
        if not player or not player.current_track:
            await interaction.response.send_message(
                "ℹ️ No track is currently playing.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎶 Now Playing",
            description=f"[{player.current_track.title}]({player.current_track.url})",
            color=EMBED_COLOR,
        )
        embed.set_thumbnail(url=player.current_track.thumbnail)
        embed.add_field(
            name="Duration", value=player.current_track.duration, inline=True
        )
        if player.current_track.uploader:
            embed.add_field(
                name="Uploader", value=player.current_track.uploader, inline=True
            )

        if player.queue:
            embed.add_field(
                name="Next Up",
                value=f"[{player.queue[0].title}]({player.queue[0].url})",
                inline=True,
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="pause", description="Pause the current track.")
    async def pause(self, interaction: discord.Interaction):
        """Pause playback."""
        player = self.players.get(interaction.guild.id)
        if not player or not player.voice_client:
            await interaction.response.send_message(
                "❌ I'm not playing anything.", ephemeral=True
            )
            return

        if player.voice_client.is_playing():
            player.voice_client.pause()
            player.state = PlayerState.PAUSED
            await interaction.response.send_message("⏸ Playback paused.")
        else:
            await interaction.response.send_message(
                "ℹ️ Playback is already paused.", ephemeral=True
            )

    @app_commands.command(name="resume", description="Resume playback.")
    async def resume(self, interaction: discord.Interaction):
        """Resume playback."""
        player = self.players.get(interaction.guild.id)
        if not player or not player.voice_client:
            await interaction.response.send_message(
                "❌ I'm not in a voice channel.", ephemeral=True
            )
            return

        if player.voice_client.is_paused():
            player.voice_client.resume()
            player.state = PlayerState.PLAYING
            await interaction.response.send_message("▶️ Playback resumed.")
        else:
            await interaction.response.send_message(
                "ℹ️ Playback is not paused.", ephemeral=True
            )

    @app_commands.command(
        name="loop", description="Toggle looping of the current track."
    )
    async def loop(self, interaction: discord.Interaction):
        """Toggle track looping."""
        player = self.players.get(interaction.guild.id)
        if not player or not player.current_track:
            await interaction.response.send_message(
                "❌ No track is currently playing.", ephemeral=True
            )
            return

        player.loop = not player.loop
        status = "enabled" if player.loop else "disabled"
        await interaction.response.send_message(f"🔁 Loop {status}.")

    @app_commands.command(name="clear", description="Clear the queue.")
    async def clear(self, interaction: discord.Interaction):
        """Clear the queue."""
        player = self.players.get(interaction.guild.id)
        if not player or not player.queue:
            await interaction.response.send_message(
                "ℹ️ The queue is already empty.", ephemeral=True
            )
            return

        player.queue.clear()
        await interaction.response.send_message("🗑️ Queue cleared.")

    @app_commands.command(name="lyrics", description="Get lyrics for a song.")
    @app_commands.describe(
        query="Song name to search lyrics for (default: current track)"
    )
    async def lyrics(
        self, interaction: discord.Interaction, query: Optional[str] = None
    ):
        """Fetch and display lyrics."""
        await interaction.response.defer()

        # Use current track if no query provided
        if not query:
            player = self.players.get(interaction.guild.id)
            if player and player.current_track:
                query = player.current_track.title
            else:
                await interaction.followup.send(
                    "❌ No track is playing and no query provided.", ephemeral=True
                )
                return

        response = await get_lyrics(track_name=query)

        if response.error_message:
            await interaction.followup.send(response.error_message)
            logger.warning(f"Lyrics error: {response.error_message}")
            return

        if response.status == 404:
            await interaction.followup.send(f"❌ No lyrics found for **{query}**.")
            return

        if response.status != 200:
            await interaction.followup.send(
                f"❌ Failed to fetch lyrics (Status: {response.status})"
            )
            return

        # Send lyrics in chunks to avoid message length limits
        for i, chunk in enumerate(response.text):
            embed = discord.Embed(
                title=f"🎵 {response.title}" if i == 0 else None,
                description=chunk,
                color=EMBED_COLOR,
            )
            await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    """Add the cog to the bot."""
    await bot.add_cog(MusicCog(bot))
