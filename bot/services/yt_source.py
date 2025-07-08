<<<<<<< HEAD
import asyncio
<<<<<<< HEAD
from dataclasses import dataclass
from typing import Dict, List, Optional, Union
from urllib.parse import urlparse

from yt_dlp import YoutubeDL

from bot.utils.logger import setup_logger

# Constants
MAX_SEARCH_RESULTS = 5
MAX_PLAYLIST_LENGTH = 100  # Prevent processing excessively large playlists
DEFAULT_REQUEST_TIMEOUT = 10  # seconds

logger = setup_logger(
    name="yt_source", log_level="INFO", log_to_file=True, log_file="yt-dlp.log"
)


@dataclass
class Track:
    """Represents an audio track with metadata."""

    title: str
    duration: int  # Duration in seconds
    url: str  # Webpage URL
    audio_url: str  # Direct audio stream URL
    uploader: Optional[str] = None  # Channel/uploader name
    thumbnail: Optional[str] = None  # Thumbnail image URL
    uploader_url: Optional[str] = None  # URL to uploader's channel

    @property
    def formatted_duration(self) -> str:
        """Format duration as HH:MM:SS or MM:SS."""
        minutes, seconds = divmod(self.duration, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


class TrackFetcher:
    """Fetches tracks and playlists from YouTube with metadata."""

    _ydl_options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "socket_timeout": DEFAULT_REQUEST_TIMEOUT,
        "extractor_args": {
            "youtube": {
                "player_client": ["web"],  # Only use web client for metadata
                "max_comments": [0],  # Don't fetch comments
            }
        },
        "format": "bestaudio/best",
        "noplaylist": False,  # Allow playlist processing
    }

    @classmethod
    async def _fetch_metadata(
        cls, query: str, is_playlist: bool = False, full_metadata: bool = False
    ) -> List[Dict]:
        """
        Fetch metadata from YouTube using yt-dlp.

        Args:
            query: URL or search query
            is_playlist: Whether to expect playlist results
            full_metadata: Whether to fetch extended metadata

        Returns:
            List of metadata dictionaries
        """
        options = cls._ydl_options.copy()
        options["extract_flat"] = not full_metadata

        if is_playlist:
            options["playlistend"] = MAX_PLAYLIST_LENGTH

        def _sync_fetch() -> List[Dict]:
            """Synchronous metadata fetching."""
            with YoutubeDL(options) as ydl:
                try:
                    info = ydl.extract_info(query, download=False)
                    if is_playlist:
                        result = info.get("entries", [])
                    else:
                        result = info.get("entries", [info])
                    return result
                except Exception as e:
                    logger.error(f"Error fetching metadata: {e}")
                    return []

        return await asyncio.to_thread(_sync_fetch)

    @classmethod
    async def fetch_track_by_name(
        cls, name: str, max_results: int = MAX_SEARCH_RESULTS
    ) -> Dict[str, str]:
        """
        Search for tracks by name.

        Args:
            name: Search query
            max_results: Maximum number of results to return

        Returns:
            Dictionary mapping titles to URLs
        """
        query = f"ytsearch{max_results}:{name}"
        results = await cls._fetch_metadata(query)

        if not results:
            logger.warning(f"No results found for query: {name}")
            return {}

        return {entry["title"]: entry["url"] for entry in results}

    @classmethod
    async def fetch_track_by_url(cls, url: str) -> Optional[Track]:
        """
        Fetch complete track metadata by URL.

        Args:
            url: YouTube video URL

        Returns:
            Track object if successful, None otherwise
        """
        results = await cls._fetch_metadata(url, full_metadata=True)
        if not results:
            return None

        result = results[0]
        if result.get("is_unavailable"):
            logger.error(f"Unavailable or deleted track: {url}")
            return None

        return cls._create_track_from_data(result)

    @classmethod
    async def fetch_playlist(cls, playlist_url: str) -> Dict[str, str]:
        """
        Fetch all tracks in a playlist.

        Args:
            playlist_url: YouTube playlist URL

        Returns:
            Dictionary mapping titles to URLs
        """
        entries = await cls._fetch_metadata(playlist_url, is_playlist=True)

        if not entries:
            logger.warning(f"Empty or invalid playlist: {playlist_url}")
            return {}

        return {
            entry["title"]: entry["url"]
            for entry in entries
            if entry and "url" in entry
        }

    @classmethod
    def _create_track_from_data(cls, data: Dict) -> Track:
        """
        Create a Track object from raw metadata.

        Args:
            data: Raw metadata dictionary

        Returns:
            Track object
        """
        # Get uploader URL if available
        uploader_url = None
        if data.get("uploader_id"):
            uploader_url = f"https://youtube.com/channel/{data['uploader_id']}"
        elif data.get("channel_url"):
            uploader_url = data["channel_url"]

        return Track(
            title=data.get("title", "Unknown Title"),
            url=data.get("webpage_url", data.get("url", "")),
            audio_url=data.get("url", ""),
            duration=int(data.get("duration", 0)),
            uploader=data.get("uploader"),
            thumbnail=data.get("thumbnail"),
            uploader_url=uploader_url,
        )

    @classmethod
    def is_valid_url(cls, url: str) -> bool:
        """
        Validate if a URL is a potentially valid YouTube URL.

        Args:
            url: URL to validate

        Returns:
            True if valid YouTube URL, False otherwise
        """
        try:
            parsed = urlparse(url)
            return (
                parsed.scheme in ("http", "https")
                and parsed.netloc in ("youtube.com", "www.youtube.com", "youtu.be")
                and any(key in parsed.path for key in ("watch", "playlist"))
            )
        except:
            return False
=======
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
>>>>>>> f5ed92a (logger, better code, fixes)
=======
import asyncio
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Optional

from yt_dlp import YoutubeDL

from bot.utils.logger import setup_logger

MAX_SEARCH_RESULTS = 5
MAX_QUEUE_LENGTH = 30
DEFAULT_REQUEST_TIMEOUT = 10

logger = setup_logger(name="yt_source", log_file="yt-dlp.log")


@dataclass
class Track:
    """Represents an audio track with metadata."""

    title: str
    duration: int  # In seconds
    url: str  # YouTube page URL
    audio_url: str  # Direct audio stream
    uploader: Optional[str] = None
    thumbnail: Optional[str] = None
    uploader_url: Optional[str] = None

    @property
    def formatted_duration(self) -> str:
        """Return duration in HH:MM:SS or MM:SS format."""
        minutes, seconds = divmod(self.duration, 60)
        hours, minutes = divmod(minutes, 60)
        return (
            f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"
        )


class TrackFetcher:
    """Interface for querying YouTube audio content."""

    _ydl_options = {
        "format": "bestaudio/best",
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "socket_timeout": DEFAULT_REQUEST_TIMEOUT,
        "noplaylist": False,
        # "external_downloader": "aria2c", # idk if it's working faster or not
        # "external_downloader_args": ["-x", "16", "-k", "1M"],
    }

    @classmethod
    async def __fetch_metadata(
        cls, query: str, is_playlist: bool = False, full_metadata: bool = False
    ) -> List[Dict]:
        options = cls._ydl_options.copy()
        options["extract_flat"] = not full_metadata
        options["noplaylist"] = not is_playlist
        if is_playlist:
            options["playlistend"] = MAX_QUEUE_LENGTH

        def _run() -> List[Dict]:
            try:
                with YoutubeDL(options) as ydl:
                    info = ydl.extract_info(query, download=False)
                    if is_playlist:
                        return info.get("entries", [])
                    return info.get("entries", [info])
            except Exception as e:
                logger.error(f"yt-dlp failed for '{query}': {e}", exc_info=True)
                return []

        return await asyncio.to_thread(_run)

    @classmethod
    def __create_track_from_data(cls, data: Dict) -> Track:
        uploader_url = None
        if uid := data.get("uploader_id"):
            uploader_url = f"https://youtube.com/channel/{uid}"
        elif ch_url := data.get("channel_url"):
            uploader_url = ch_url

        return Track(
            title=data.get("title", "Unknown Title"),
            url=data.get("webpage_url", data.get("url", "")),
            audio_url=data.get("url", ""),
            duration=int(data.get("duration", 0)),
            uploader=data.get("uploader"),
            thumbnail=data.get("thumbnail"),
            uploader_url=uploader_url,
        )

    @classmethod
    async def fetch_track_by_name(
        cls, name: str, max_results: int = MAX_SEARCH_RESULTS
    ) -> Dict[str, str]:
        query = f"ytsearch{max_results}:{name}"
        results = await cls.__fetch_metadata(query)
        if not results:
            logger.warning(f"No matches for search: {name}")
            return {}
        return {
            entry["title"]: entry["url"]
            for entry in results
            if "title" in entry and "url" in entry
        }

    @classmethod
    async def fetch_track_by_url(cls, url: str) -> Optional[Track]:
        results = await cls.__fetch_metadata(url, full_metadata=True)
        if not results:
            logger.warning(f"No metadata returned for URL: {url}")
            return None

        entry = results[0]
        if entry.get("is_unavailable"):
            logger.error(f"Track unavailable: {url}")
            return None

        return cls.__create_track_from_data(entry)

    @classmethod
    async def fetch_playlist(cls, playlist_url: str) -> AsyncGenerator[str, None]:
        """Async generator yielding track URLs from a playlist as soon as they're fetched."""
        entries = await cls.__fetch_metadata(playlist_url, is_playlist=True)

        if not entries:
            logger.warning(f"Empty or invalid playlist: {playlist_url}")
            return

        for entry in entries:
            if entry and "url" in entry:
                yield entry["url"]
>>>>>>> 489c3f3 (changed to ffmpegOpus, added shuffle, skip, help commands, better playlist handling)
