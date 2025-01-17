from bot.utils.logger import discord_logger, bot_logger
import discord
from discord.ext import commands
from discord import app_commands
import re

from bot.services.yt_source import (
    TrackSelectView,
    fetch_track_by_url,
    fetch_track_by_name,
    fetch_playlist,
    get_audio,
    Track,
    Playlist,
)
from bot.services.get_lyrics import get_lyrics


class MusicCog(commands.Cog):
    """Cog for music-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_clients: dict[int, discord.VoiceClient] = (
            {}
        )  # Guild-specific voice clients
        self.queue: dict[int, list[Track]] = {}  # Guild-specific music queue
        self.current_tracks: dict[int, Track] = (
            {}
        )  # Guild-specific currently playing track

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        for guild_id, voice_client in list(self.voice_clients.items()):
            if voice_client.is_connected() and len(voice_client.channel.members) == 1:
                await voice_client.disconnect()
                self.__clear_guild_data(guild_id)
                bot_logger.info(
                    f"Disconnected from the empty channel {voice_client.channel.id}"
                )

    def __clear_guild_data(self, guild_id: int):
        """Clears the guild-specific data."""
        self.voice_clients.pop(guild_id, None)
        self.queue.pop(guild_id, None)
        self.current_tracks.pop(guild_id, None)

    async def ensure_voice_client(self, interaction: discord.Interaction) -> bool:
        """Ensure the bot is connected to the voice channel."""
        guild_id = interaction.guild_id
        if (
            guild_id not in self.voice_clients
            or not self.voice_clients[guild_id].is_connected()
        ):
            if interaction.user.voice:
                channel = interaction.user.voice.channel
                self.voice_clients[guild_id] = await channel.connect()
            else:
                await interaction.response.send_message(
                    "You must be in a voice channel.", ephemeral=True
                )
                return False
        return True

    # ====================JOIN/LEAVE====================
    @app_commands.command(name="join", description="Join the user's voice channel.")
    async def join(self, interaction: discord.Interaction):
        """Join the user's voice channel."""
        if await self.ensure_voice_client(interaction):
            await interaction.response.send_message("🔊Joined the voice channel!")
            bot_logger.info(f"Joined the voice channel {interaction.channel_id}")

    @app_commands.command(name="leave", description="👋Leave the voice channel.")
    async def leave(self, interaction: discord.Interaction):
        """Leave the voice channel."""
        guild_id = interaction.guild_id
        if guild_id in self.voice_clients:
            await self.voice_clients[guild_id].disconnect()
            self.__clear_guild_data(guild_id)
            await interaction.response.send_message(
                "👋Disconnected from the voice channel."
            )
            bot_logger.info(f"Left the voice channel {interaction.channel_id}")
        else:
            await interaction.response.send_message(
                "🔌Not connected to a voice channel.", ephemeral=True
            )

    # =======================PLAY=======================
    @app_commands.command(
        name="play", description="Play a track/playlist from a URL or by name."
    )
    async def play(self, interaction: discord.Interaction, name_or_url: str):
        """Play a track/playlist from a URL or by name."""
        if not await self.ensure_voice_client(interaction):
            return

        guild_id = interaction.guild_id
        if guild_id not in self.queue:
            self.queue[guild_id] = []

        await interaction.response.defer()

        # If the input is a URL
        if re.match(r"https.*youtu[.]?be", name_or_url):
            if "playlist" in name_or_url:
                await self.__handle_playlist(
                    interaction=interaction, guild_id=guild_id, url=name_or_url
                )
            else:
                await self.__handle_track_by_url(
                    interaction=interaction, guild_id=guild_id, url=name_or_url
                )
        else:
            await self.__handle_track_search(interaction, guild_id, name_or_url)

        if (
            guild_id not in self.current_tracks
            or not self.voice_clients[guild_id].is_playing()
        ):
            await self.play_next_track(interaction.guild_id, interaction.channel)

    async def __send_added_to_queue_message(
        self,
        interaction: discord.Interaction,
        response_text: str,
        thumbnail: str | None = None,
    ):
        embed = discord.Embed(
            title="Added to queue",
            description=response_text,
            color=discord.Color.blue(),
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        await interaction.edit_original_response(embed=embed, view=None)

    async def __handle_playlist(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        url: str,
    ):
        """Handle playlist fetching"""
        playlist = await fetch_playlist(url)
        self.queue[guild_id].extend(playlist.tracks)
        await self.__send_added_to_queue_message(
            interaction=interaction, response_text=str(playlist)
        )
        bot_logger.info(f"Playlist added {playlist.url}")

    async def __handle_track_by_url(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        url: str,
    ):
        """Handle track url fetching"""
        track = await fetch_track_by_url(url)
        if track is None:
            await interaction.edit_original_response(content="Unable to add the track")
            return
        self.queue[guild_id].append(track)
        await self.__send_added_to_queue_message(
            interaction=interaction,
            response_text=str(track),
            thumbnail=track.thumbnail,
        )
        bot_logger.info(f"Track added {track.url}")

    async def __handle_track_search(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        name: str,
    ):
        """Handle track search by name."""
        tracks_found = await fetch_track_by_name(name)
        view = TrackSelectView(tracks=tracks_found)
        embed = discord.Embed(
            title="🎵Choose the track",
            description="\n".join(
                [
                    f"{i + 1}. [{track.title}]({track.url})"
                    for i, track in enumerate(tracks_found)
                ]
            ),
            color=discord.Color.blue(),
        )
        await interaction.edit_original_response(embed=embed, view=view)
        await view.wait()
        bot_logger.info(f"Track selected {view.selected_track.url}")

        if view.selected_track:
            track = await fetch_track_by_url(view.selected_track.url)
            self.queue[guild_id].append(track)

            await self.__send_added_to_queue_message(
                interaction, str(track), track.thumbnail
            )

    async def play_next_track(self, guild_id: int, channel: discord.TextChannel):
        """Play the next track in the queue."""
        if guild_id in self.queue and self.queue[guild_id]:
            track: Track = self.queue[guild_id].pop(0)
            self.current_tracks[guild_id] = track
            voice_client = self.voice_clients[guild_id]

            audio = await get_audio(track.url)
            if audio is None:
                bot_logger.error(f"Unable to fetch the audio for {track.url}")
                await channel.send(f"Unable to play the track")
                await self.play_next_track(guild_id, channel)
            else:
                voice_client.play(
                    audio,
                    after=lambda e: self.bot.loop.create_task(
                        self.play_next_track(guild_id, channel)
                    ),
                )  # Play the audio stream from FFmpegPCMAudio

                bot_logger.info(f"Playing {track.url}")
                embed = discord.Embed(
                    title="🎶Now Playing",
                    description=str(track),
                    color=discord.Color.blue(),
                )
                if track.thumbnail:
                    embed.set_thumbnail(url=track.thumbnail)
                await channel.send(embed=embed)

    # =======================SKIP=======================
    @app_commands.command(
        name="skip", description="Skip the current (0) or specific tracks."
    )
    @app_commands.describe(
        range_or_id="0 - to skip the current track, index - to skip from the queue"
    )
    async def skip_track(
        self, interaction: discord.Interaction, range_or_id: str = "0"
    ):
        """Skip tracks in the queue."""
        guild_id = interaction.guild_id
        if guild_id not in self.voice_clients:
            await interaction.response.send_message(
                "🔌Not connected to a voice channel."
            )
            return
        if not self.voice_clients[guild_id].is_playing():
            await interaction.response.send_message("No track is currently playing.")
            return

        if range_or_id == "0":
            current_track = self.current_tracks.get(guild_id)
            self.voice_clients[guild_id].stop()
            if not self.queue[guild_id]:
                del self.current_tracks[guild_id]
            await interaction.response.send_message(
                f"⏭️Skipped the current track: {current_track.title}"
            )
            bot_logger.info(f"Current track skipped {current_track.url}")
        elif range_or_id.isdigit():
            track_id = int(range_or_id)
            if 1 <= track_id <= len(self.queue[guild_id]):
                skipped_track = self.queue[guild_id].pop(track_id - 1)
                await interaction.response.send_message(
                    f"⏭️Skipped track: {skipped_track.title}"
                )
                bot_logger.info(f"Track skipped {skipped_track.url}")
            else:
                await interaction.response.send_message("❌Invalid track number.")
        else:
            await interaction.response.send_message("❌Invalid track number format.")

    # ===================LIST/CURRENT===================
    @app_commands.command(name="list", description="List the current queue.")
    async def show_track_list(self, interaction: discord.Interaction):
        """List the tracks currently in the queue."""
        guild_id = interaction.guild_id
        queue = self.queue.get(guild_id, [])
        if not queue:
            await interaction.response.send_message("The queue is empty.")
            return
        track_list = "\n".join(
            [f"{i + 1}. {track.title}" for i, track in enumerate(queue)]
        )
        embed = discord.Embed(
            title="📜Queue",
            description=track_list,
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="current", description="Show the current playing track.")
    async def show_current_track(self, interaction: discord.Interaction):
        """Show the current playing track."""
        guild_id = interaction.guild_id
        track = self.current_tracks.get(guild_id)
        if track:
            embed = discord.Embed(
                title="🎶Now Playing",
                description=str(track),
                color=discord.Color.blue(),
            )
            if track.thumbnail:
                embed.set_thumbnail(url=track.thumbnail)
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("No track is currently playing.")

    # ===================PAUSE/RESUME===================
    @app_commands.command(
        name="pause", description="Pause the currently playing track."
    )
    async def pause(self, interaction: discord.Interaction):
        """Pause the currently playing track."""
        guild_id = interaction.guild_id
        if guild_id in self.voice_clients and self.voice_clients[guild_id].is_playing():
            self.voice_clients[guild_id].pause()
            await interaction.response.send_message("⏸️Paused the track.")
        else:
            await interaction.response.send_message("No track is currently playing.")

    @app_commands.command(name="resume", description="Resume the paused track.")
    async def resume(self, interaction: discord.Interaction):
        """Resume the currently paused track."""
        guild_id = interaction.guild_id
        if guild_id in self.voice_clients and self.voice_clients[guild_id].is_paused():
            self.voice_clients[guild_id].resume()
            await interaction.response.send_message("▶️Resumed the track.")
        else:
            await interaction.response.send_message(
                "No track is currently paused.",
            )

    # ======================LYRICS======================
    @app_commands.command(
        name="lyrics", description="Get the lyrics of a specific song."
    )
    async def get_lyrics(self, interaction: discord.Interaction, track_name: str):
        """Fetch lyrics for the specified track."""
        await interaction.response.defer()
        response = await get_lyrics(track_name)

        if response.error_message:
            await interaction.followup.send(response.error_message)
            bot_logger.warning(f"{response.error_message}")

        elif response.status == 404:
            await interaction.followup.send(f"❌ No lyrics found for **{track_name}**.")
            bot_logger.warning(f"No lyrics found for {track_name}")
        elif response.status != 200:
            await interaction.followup.send(
                f"❌ Unable to fetch lyrics. Status: {response.status}"
            )
            bot_logger.error(
                f"Unable to fetch the lyrics for {track_name} {response.status}"
            )
        else:
            for i, chunk in enumerate(response.text):
                embed = discord.Embed(
                    title=f"**{response.title}**" if i == 0 else None,
                    description=chunk,
                    color=discord.Color.blue(),
                )

                await interaction.followup.send(embed=embed)


async def setup(bot):
    """Setup function to load the cog."""
    await bot.add_cog(MusicCog(bot))
