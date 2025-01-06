import asyncio
import discord
from yt_dlp import YoutubeDL
from discord import FFmpegPCMAudio
from dataclasses import dataclass
from bot.utils.logger import yt_source_logger


# =====================CLASSES======================
@dataclass
class Track:
    """Represents a song with title, duration, thumbnail, and URL."""

    title: str
    duration: int  # Duration in seconds
    url: str  # Webpage url
    thumbnail: str | None = None  # Optional thumbnail image URL

    def __str__(self):
        return f"Title: [{self.title}](<{self.url}>)\nDuration: {self.duration}s"


@dataclass
class Playlist:
    """Represents a playlist with title, duration, thumbnail, and URL."""

    title: str
    url: str
    tracks: list[Track]

    @property
    def duration(self) -> int:
        return sum(
            [song.duration if song.duration is not None else 0 for song in self.tracks]
        )

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    def __str__(self):
        return f"Playlist Title: [{self.title}](<{self.url}>)\nDuration: {self.duration}s\nSongs Count: {self.track_count}"


# =======================VIEW=======================
class TrackSelectButton(discord.ui.Button):
    def __init__(self, label, track: Track, style=discord.ButtonStyle.primary):
        super().__init__(label=label, style=style)
        self.track = track

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_track = self.track
        await interaction.response.defer()
        self.view.stop()


class CancelButton(discord.ui.Button):
    def __init__(self, label="Cancel", style=discord.ButtonStyle.danger):
        super().__init__(label=label, style=style)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.view.stop()


class TrackSelectView(discord.ui.View):
    def __init__(self, tracks: list[Track]):
        super().__init__(timeout=60)
        self.selected_track = None
        for i, track in enumerate(tracks, start=1):
            self.add_item(TrackSelectButton(label=str(i), track=track))
        self.add_item(CancelButton())


# =================GLOBAL VARIABLES=================

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


# def __fetch_info(url: str) -> dict | None:
#     with YoutubeDL(YTDL_OPTIONS) as ydl:
#         return ydl.extract_info(url, download=False)


# def __parse_track(track_info: dict) -> Track:
#     track = Track(
#         title=track_info.get("title", "Unknown Title"),
#         duration=track_info.get("duration", 0),
#         url=track_info.get("webpage_url", track_info.get("url")),
#         thumbnail=track_info.get("thumbnail"),
#     )
#     return track


# async def fetch_track_by_url(url: str) -> Track | None:
#     """Parses a single song"""
#     track_info = await asyncio.to_thread(lambda: __fetch_info(url))
#     track = __parse_track(track_info)
#     return track


# async def fetch_playlist(url: str) -> Playlist:
#     """Parses a playlist"""
#     playlist_info = await asyncio.to_thread(lambda: __fetch_info(url))
#     playlist = Playlist(
#         title=playlist_info.get("title", "Unknown Title"),
#         url=playlist_info.get("webpage_url"),
#         tracks=[__parse_track(entry) for entry in playlist_info["entries"]],
#     )
#     return playlist


# async def fetch_track_by_name(name: str) -> list[Track]:
#     """Fetches a single song by name"""
#     entries = await asyncio.to_thread(
#         lambda: __fetch_info(f"ytsearch{ENTRIES_COUNT}:{name}")
#     )
#     tracks = [__parse_track(entry) for entry in entries["entries"]]
#     return tracks


# async def get_audio(url: str) -> FFmpegPCMAudio:
#     """Returns an audio object for the given url"""
#     track = await asyncio.to_thread(lambda: __fetch_info(url))
#     audio_url = track.get("url")
#     return FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)


def __fetch_info(url: str) -> dict | None:
    try:
        with YoutubeDL(YTDL_OPTIONS) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        if "This video is unavailable" in str(e) or "Video unavailable" in str(e):
            yt_source_logger.error(f"Video is unavailable or deleted: {url}")
        else:
            yt_source_logger.error(f"Error fetching info for {url}: {e}")
    return None


def __parse_track(track_info: dict) -> Track | None:
    if not track_info or track_info.get("is_unavailable"):
        yt_source_logger.error("Skipping unavailable or deleted track.")
        return None
    return Track(
        title=track_info.get("title", "Unknown Title"),
        duration=track_info.get("duration", 0),
        url=track_info.get("webpage_url", track_info.get("url")),
        thumbnail=track_info.get("thumbnail"),
    )


async def fetch_track_by_url(url: str) -> Track | None:
    track_info = await asyncio.to_thread(lambda: __fetch_info(url))
    if not track_info:
        return None
    track = __parse_track(track_info)
    return track


async def fetch_playlist(url: str) -> Playlist | None:
    playlist_info = await asyncio.to_thread(lambda: __fetch_info(url))
    if not playlist_info or "entries" not in playlist_info:
        yt_source_logger.error(f"Failed to fetch playlist or no entries found: {url}")
        return None

    tracks = []
    for entry in playlist_info["entries"]:
        if entry:
            track = __parse_track(entry)
            if track:
                tracks.append(track)
    return Playlist(
        title=playlist_info.get("title", "Unknown Title"),
        url=playlist_info.get("webpage_url"),
        tracks=tracks,
    )


async def fetch_track_by_name(name: str) -> list[Track]:
    entries = await asyncio.to_thread(
        lambda: __fetch_info(f"ytsearch{ENTRIES_COUNT}:{name}")
    )
    if not entries or "entries" not in entries:
        yt_source_logger.error(f"No results found for: {name}")
        return []
    tracks = [__parse_track(entry) for entry in entries["entries"] if entry]
    return [track for track in tracks if track is not None]


async def get_audio(url: str) -> FFmpegPCMAudio | None:
    track = await asyncio.to_thread(lambda: __fetch_info(url))
    if not track:
        yt_source_logger.error(f"Failed to fetch audio for: {url}")
        return None
    audio_url = track.get("url")
    if not audio_url:
        yt_source_logger.error(f"Audio URL not found for: {url}")
        return None
    return FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
