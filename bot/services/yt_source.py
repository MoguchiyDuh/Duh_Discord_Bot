import asyncio
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Optional

from yt_dlp import YoutubeDL

from bot.cogs import MAX_QUEUE_LENGTH
from bot.utils.logger import setup_logger

MAX_SEARCH_RESULTS = 5
DEFAULT_REQUEST_TIMEOUT = 10

logger = setup_logger(name="yt_source", log_file="yt-dlp.log")


# ========== AUDIO STREAMING ==========
@dataclass
class Track:
    """Represents an audio track with metadata."""

    title: str
    url: str  # Audio page URL
    audio_url: str  # Direct audio stream
    duration: Optional[int] = None  # In seconds
    thumbnail: Optional[str] = None
    author: Optional[str] = None
    author_url: Optional[str] = None

    @property
    def formatted_duration(self) -> Optional[str]:
        """Return duration in HH:MM:SS or MM:SS format."""
        if self.duration:
            minutes, seconds = divmod(self.duration, 60)
            hours, minutes = divmod(minutes, 60)
            return (
                f"{hours}:{minutes:02}:{seconds:02}"
                if hours
                else f"{minutes}:{seconds:02}"
            )
        else:
            return None


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
        logger.debug(
            f"Fetching metadata for query: {query}, playlist={is_playlist}, full={full_metadata}"
        )
        options = cls._ydl_options.copy()
        options["extract_flat"] = not full_metadata
        options["noplaylist"] = not is_playlist
        if is_playlist:
            options["playlistend"] = MAX_QUEUE_LENGTH

        def _run() -> List[Dict]:
            try:
                with YoutubeDL(options) as ydl:
                    info = ydl.extract_info(query, download=False)
                    logger.debug(f"Metadata fetched successfully for: {query}")
                    if is_playlist:
                        return info.get("entries", [])
                    return info.get("entries", [info])
            except Exception as e:
                logger.error(f"yt-dlp failed for '{query}': {e}", exc_info=True)
                return []

        return await asyncio.to_thread(_run)

    @classmethod
    def __create_track_from_data(cls, data: Dict) -> Track:
        logger.debug(f"Creating Track from data: {data.get('title', 'No Title')}")
        author_url = None
        if uid := data.get("uploader_id"):
            author_url = f"https://youtube.com/channel/{uid}"
        elif ch_url := data.get("channel_url"):
            author_url = ch_url

        duration = (
            int(data["duration"])
            if isinstance(data.get("duration"), (str, int, float))
            else None
        )

        track = Track(
            title=data.get("title", "Unknown Title"),
            url=data.get("webpage_url", data.get("url", "")),
            audio_url=data.get("url", ""),
            duration=duration,
            thumbnail=data.get("thumbnail"),
            author=data.get("uploader"),
            author_url=author_url,
        )
        logger.debug(f"Track created: {track.title} [{track.formatted_duration}]")
        return track

    @classmethod
    async def fetch_track_by_name(
        cls, name: str, max_results: int = MAX_SEARCH_RESULTS
    ) -> Dict[str, str]:
        logger.debug(f"Searching for track by name: '{name}' (max {max_results})")
        query = f"ytsearch{max_results}:{name}"
        results = await cls.__fetch_metadata(query, full_metadata=True)
        if not results:
            logger.warning(f"No matches for search: {name}")
            return {}

        titles = [entry["title"] for entry in results if "title" in entry]
        logger.debug(f"Found {len(titles)} result(s) for '{name}': {titles}")

        return {
            entry["title"]: entry["url"]
            for entry in results
            if "title" in entry and "url" in entry
        }

    @classmethod
    async def fetch_track_by_url(cls, url: str) -> Optional[Track]:
        logger.debug(f"Fetching track metadata from URL: {url}")
        results = await cls.__fetch_metadata(url, full_metadata=True)
        if not results:
            logger.warning(f"No metadata returned for URL: {url}")
            return None

        entry = results[0]
        if entry.get("is_unavailable"):
            logger.error(f"Track marked as unavailable: {url}")
            return None

        logger.debug(f"Metadata received for URL: {url}, creating Track")
        return cls.__create_track_from_data(entry)

    @classmethod
    async def fetch_playlist(cls, playlist_url: str) -> AsyncGenerator[str, None]:
        """Async generator yielding track URLs from a playlist as soon as they're fetched."""
        logger.debug(f"Fetching playlist from URL: {playlist_url}")
        entries = await cls.__fetch_metadata(playlist_url, is_playlist=True)

        if not entries:
            logger.warning(f"Empty or invalid playlist: {playlist_url}")
            return

        logger.debug(f"Yielding {len(entries)} track(s) from playlist: {playlist_url}")
        for entry in entries:
            if entry and "url" in entry:
                logger.debug(f"Yielding track URL: {entry['url']}")
                yield entry["url"]
