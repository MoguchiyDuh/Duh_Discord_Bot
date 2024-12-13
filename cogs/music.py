import discord
from discord.ext import commands
from discord import app_commands

import os
import sys

sys.path.append(os.path.dirname(__file__) + "/..")
from utils.yt_source import YTDLSource


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.queues = {}
        self.current_tracks = {}

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        for guild_id, voice_client in list(self.voice_clients.items()):
            if voice_client.is_connected():
                members = voice_client.channel.members
                if len(members) == 1 and members[0] == self.bot.user:
                    await voice_client.disconnect()
                    del self.voice_clients[guild_id]
                    print(
                        f"Disconnected from empty channel {voice_client.channel.name}."
                    )

    @app_commands.command(name="join", description="Join a voice channel")
    async def join(self, interaction: discord.Interaction):
        # if user is in vc
        if interaction.user.voice:
            guild_id = interaction.guild.id
            channel = interaction.user.voice.channel

            # if in the current server
            if guild_id in self.voice_clients:
                voice_client = self.voice_clients[guild_id]
                # if already in vc
                if voice_client.is_connected() and voice_client.channel == channel:
                    await interaction.response.send_message(
                        f"I'm already in {channel.name}."
                    )
                    return

                await voice_client.disconnect()

            voice_client = await channel.connect()
            self.voice_clients[guild_id] = voice_client
            await interaction.response.send_message(f"Joined {channel.name}.")
        else:
            await interaction.response.send_message(
                "You need to be in a voice channel to use this command."
            )

    @app_commands.command(name="leave", description="Leave the voice channel")
    async def leave(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        # if in vc
        if guild_id in self.voice_clients:
            await self.voice_clients[guild_id].disconnect()
            del self.voice_clients[guild_id]
            self.queues.pop(guild_id, None)
            self.current_tracks.pop(guild_id, None)
            await interaction.response.send_message(
                "Disconnected from the voice channel."
            )
        else:
            await interaction.response.send_message(
                "I'm not connected to a voice channel."
            )

    @app_commands.command(name="play", description="Play a song from URL")
    async def play(self, interaction: discord.Interaction, url: str):
        guild_id = interaction.guild.id
        # connect if not in vc
        if guild_id not in self.voice_clients:
            await self.join(interaction)

        if guild_id in self.voice_clients:
            async with interaction.channel.typing():
                player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
                # making a server queue
                if guild_id not in self.queues:
                    self.queues[guild_id] = []

                self.queues[guild_id].append(player)
                await interaction.response.send_message(
                    f"Added to queue: {player.title}"
                )
                # adding current track
                if guild_id not in self.current_tracks:
                    await self.play_next(guild_id, interaction)

    async def play_next(self, guild_id, interaction):
        if guild_id in self.queues and self.queues[guild_id]:
            player = self.queues[guild_id].pop(0)
            self.current_tracks[guild_id] = player
            voice_client = self.voice_clients[guild_id]

            def after_playing(error):
                if error:
                    print(f"Error while playing: {error}")
                self.bot.loop.create_task(self.play_next(guild_id, interaction))

            voice_client.play(player, after=after_playing)
            await interaction.followup.send(f"Now playing: {player.title}")
        else:
            self.current_tracks.pop(guild_id, None)

    @app_commands.command(name="skip", description="Skip a track or a range of tracks")
    async def skip(self, interaction: discord.Interaction, range_or_number: str = "0"):
        guild_id = interaction.guild.id
        if guild_id in self.voice_clients:
            if range_or_number == "0":  # Skip the currently playing track
                if self.current_tracks.get(guild_id):
                    voice_client = self.voice_clients[guild_id]
                    voice_client.stop()
                    await interaction.response.send_message(
                        "Skipped the current track."
                    )
                else:
                    await interaction.response.send_message(
                        "No track is currently playing."
                    )
            elif "-" in range_or_number:  # Skip a range of tracks
                try:
                    start, end = map(int, range_or_number.split("-"))
                    if start < 1 or end > len(self.queues[guild_id]) or start > end:
                        await interaction.response.send_message("Invalid range.")
                        return
                    skipped_tracks = self.queues[guild_id][start - 1 : end]
                    self.queues[guild_id] = (
                        self.queues[guild_id][: start - 1] + self.queues[guild_id][end:]
                    )
                    skipped_titles = "\n".join(track.title for track in skipped_tracks)
                    await interaction.response.send_message(
                        f"Skipped tracks:\n{skipped_titles}"
                    )
                except ValueError:
                    await interaction.response.send_message(
                        "Invalid range format. Use numbers like `1-3`."
                    )
            else:  # Skip a single track by number
                try:
                    track_number = int(range_or_number)
                    if 1 <= track_number <= len(self.queues[guild_id]):
                        skipped_track = self.queues[guild_id].pop(track_number - 1)
                        await interaction.response.send_message(
                            f"Skipped track: {skipped_track.title}"
                        )
                    else:
                        await interaction.response.send_message("Invalid track number.")
                except ValueError:
                    await interaction.response.send_message(
                        "Invalid track number format."
                    )
        else:
            await interaction.response.send_message(
                "I'm not connected to a voice channel."
            )

    @app_commands.command(name="list", description="List all tracks in the queue")
    async def list(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.queues and self.queues[guild_id]:
            queue_titles = "\n".join(
                f"{i+1}. {track.title}" for i, track in enumerate(self.queues[guild_id])
            )
            await interaction.response.send_message(f"Queue:\n{queue_titles}")
        else:
            await interaction.response.send_message("The queue is empty.")

    @app_commands.command(
        name="current", description="Show the currently playing track"
    )
    async def current(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.current_tracks:
            await interaction.response.send_message(
                f"Currently playing: {self.current_tracks[guild_id].title}"
            )
        else:
            await interaction.response.send_message("No track is currently playing.")

    @app_commands.command(name="pause", description="Pause the current track")
    async def pause(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.voice_clients:
            voice_client = self.voice_clients[guild_id]
            if voice_client.is_playing():
                voice_client.pause()
                await interaction.response.send_message("Playback paused.")
            else:
                await interaction.response.send_message(
                    "No track is currently playing."
                )
        else:
            await interaction.response.send_message(
                "I'm not connected to a voice channel."
            )

    @app_commands.command(name="resume", description="Resume the paused track")
    async def resume(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in self.voice_clients:
            voice_client = self.voice_clients[guild_id]
            if voice_client.is_paused():
                voice_client.resume()
                await interaction.response.send_message("Playback resumed.")
            elif voice_client.is_playing():
                await interaction.response.send_message("The track is already playing.")
            else:
                await interaction.response.send_message("No track is currently paused.")
        else:
            await interaction.response.send_message(
                "I'm not connected to a voice channel."
            )


async def setup(bot):
    await bot.add_cog(Music(bot))
