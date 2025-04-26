import asyncio
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
