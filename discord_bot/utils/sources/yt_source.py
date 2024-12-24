import asyncio
import discord
from yt_dlp import YoutubeDL
from discord import FFmpegPCMAudio

from . import Playlist, Track


# --------------------------------------------------
class TrackSelectButton(discord.ui.Button):
    def __init__(self, label, track: Track):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.track = track

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_track = self.track
        await interaction.response.defer()
        self.view.stop()


class TrackSelectView(discord.ui.View):
    def __init__(self, tracks: list[Track]):
        super().__init__(timeout=60)
        self.selected_track = None
        for i, track in enumerate(tracks, start=1):
            self.add_item(TrackSelectButton(label=str(i), track=track))


# --------------------------------------------------


class YTSource:
    """YouTube audio source using yt-dlp (for both single song and playlists)."""

    YTDL_OPTIONS = {
        "no_warnings": True,  # Suppress warnings
        "skip_download": True,  # Don't download anything
        "extract_flat": True,  # Only extract metadata (e.g., title, duration, thumbnail)
        "format": "bestaudio/best",  # For best audio info (doesn't affect title, duration, or thumbnail)
        "noplaylist": False,  # Keep playlist support
    }

    FFMPEG_OPTIONS = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn -af aresample=async=1 -filter:a 'volume=0.3'",
    }

    ENTRIES_COUNT = 5  # Number of entries to fetch for search queries

    @classmethod
    async def fetch_track_by_url(cls, url: str):
        """Fetches a single song by URL"""
        loop = asyncio.get_event_loop()
        with YoutubeDL(cls.YTDL_OPTIONS) as ytdl:
            track = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(url, download=False)
            )
            if not track:
                return None
            return cls.__get_track(track)

    @classmethod
    def __get_track(cls, entry):
        return Track(
            title=entry.get("title", "Unknown Title"),
            duration=entry.get("duration", 0),
            webpage_url=entry.get("webpage_url", entry.get("url")),
            thumbnail=entry.get("thumbnail", ""),
        )

    @classmethod
    async def fetch_playlist(cls, url: str):
        """Fetches a playlist"""
        loop = asyncio.get_event_loop()
        with YoutubeDL(cls.YTDL_OPTIONS) as ytdl:
            entries = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(url, download=False)
            )
            if not entries:
                return None
            return Playlist(
                title=entries.get("title", "Unknown Title"),
                webpage_url=entries.get("webpage_url"),
                tracks=[cls.__get_track(entry) for entry in entries["entries"]],
            )

    @classmethod
    async def fetch_track_by_name(cls, name: str):
        """Fetches a single song by name"""
        loop = asyncio.get_event_loop()
        with YoutubeDL(cls.YTDL_OPTIONS) as ytdl:
            entries = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(
                    f"ytsearch{cls.ENTRIES_COUNT}:{name}", download=False
                ),
            )
        return [cls.__get_track(entry) for entry in entries["entries"]]

    @classmethod
    async def get_audio(cls, url: str):
        loop = asyncio.get_event_loop()
        with YoutubeDL(cls.YTDL_OPTIONS) as ytdl:
            track = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(url, download=False)
            )
            if not track:
                return None
            audio_url = track.get("url")
            print(audio_url)
            return FFmpegPCMAudio(audio_url, **cls.FFMPEG_OPTIONS)
