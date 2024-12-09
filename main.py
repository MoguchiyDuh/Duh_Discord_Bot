import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp as youtube_dl
import os

intents = discord.Intents.default()
intents.message_content = True


class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        await self.setup_hook()
        logo_path = "music_bot_logo.png"
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as logo_file:
                logo = discord.File(logo_file, filename="music_bot_logo.png")
                await self.user.edit(avatar=logo.read())
        else:
            print("Logo file not found.")

    async def setup_hook(self):
        self.tree.add_command(join)
        self.tree.add_command(leave)
        self.tree.add_command(play)
        self.tree.add_command(stop)
        await self.tree.sync()


bot = MusicBot()


ytdl_format_options = {
    "format": "bestaudio/best",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ],
}
ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

ffmpeg_options = {
    "options": "-vn",
}


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("url")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=not stream)
        )

        if "entries" in data:

            data = data["entries"][0]

        filename = data["url"] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


@app_commands.command(name="join", description="Join a voice channel")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message(
            "You are not connected to a voice channel!", ephemeral=True
        )
        return

    channel = interaction.user.voice.channel
    await channel.connect()
    await interaction.response.send_message("Joined the voice channel.")


@app_commands.command(name="leave", description="Leave the voice channel")
async def leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Disconnected from the voice channel.")
    else:
        await interaction.response.send_message(
            "I'm not connected to a voice channel!", ephemeral=True
        )


@app_commands.command(name="play", description="Play a YouTube video")
async def play(interaction: discord.Interaction, url: str):
    if not interaction.guild.voice_client:
        await interaction.response.send_message(
            "I'm not connected to a voice channel!", ephemeral=True
        )
        return

    async with interaction.channel.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        interaction.guild.voice_client.play(
            player, after=lambda e: print(f"Player error: {e}") if e else None
        )
        await interaction.response.send_message(f"Now playing: {player.title}")


@app_commands.command(name="stop", description="Stop the current playback")
async def stop(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Playback stopped.")
    else:
        await interaction.response.send_message("Nothing is playing!", ephemeral=True)


load_dotenv()
TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)
