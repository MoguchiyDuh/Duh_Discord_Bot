import asyncio
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Optional

from yt_dlp import YoutubeDL

from bot.utils.config import MAX_QUEUE_LENGTH
from bot.utils.logger import setup_logger

MAX_SEARCH_RESULTS = 5
DEFAULT_REQUEST_TIMEOUT = 10

logger = setup_logger(name="yt_source", log_file="yt-dlp.log")


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
        "quiet": False,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "socket_timeout": DEFAULT_REQUEST_TIMEOUT,
        "noplaylist": True,
        "cookiefile": "./cookies.txt",
    }

    @classmethod
    async def __fetch_metadata(
        cls, query: str, is_playlist: bool = False, full_metadata: bool = True
    ) -> List[Dict]:
        logger.debug(
            f"Fetching metadata for query: {query}, playlist={is_playlist}, full={full_metadata}"
        )
        options = cls._ydl_options.copy()

        if is_playlist:
            options["noplaylist"] = False
            options["playlistend"] = MAX_QUEUE_LENGTH
            if not full_metadata:
                options["extract_flat"] = True

        if not full_metadata:
            options["extract_flat"] = True

        def _run() -> List[Dict]:
            try:
                with YoutubeDL(options) as ydl:
                    info = ydl.extract_info(query, download=False)
                    logger.debug(f"Metadata fetched successfully for: {query}")

                    if is_playlist and "entries" in info:
                        return [entry for entry in info["entries"] if entry is not None]
                    elif "entries" in info:
                        return [entry for entry in info["entries"] if entry is not None]
                    else:
                        return [info] if info else []
            except Exception as e:
                logger.error(f"yt-dlp failed for '{query}': {e}", exc_info=True)
                return []

        return await asyncio.to_thread(_run)

    @classmethod
    def __create_track_from_data(cls, data: Dict) -> Track:
        logger.debug(f"Creating Track from data: {data.get('title', 'No Title')}")

        # Handle author URL
        author_url = None
        if uid := data.get("uploader_id"):
            author_url = f"https://youtube.com/channel/{uid}"
        elif ch_url := data.get("channel_url"):
            author_url = ch_url
        elif up_url := data.get("uploader_url"):
            author_url = up_url

        # Handle duration
        duration = None
        if data.get("duration"):
            try:
                duration = int(float(data["duration"]))
            except (ValueError, TypeError):
                pass

        # Get the best audio URL
        audio_url = data.get("url", "")
        if not audio_url and data.get("formats"):
            # Find best audio format
            audio_formats = [f for f in data["formats"] if f.get("acodec") != "none"]
            if audio_formats:
                audio_url = audio_formats[0].get("url", "")

        track = Track(
            title=data.get("title", "Unknown Title"),
            url=data.get("webpage_url", data.get("original_url", "")),
            audio_url=audio_url,
            duration=duration,
            thumbnail=data.get("thumbnail"),
            author=data.get("uploader", data.get("channel")),
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
        results = await cls.__fetch_metadata(query, full_metadata=False)
        if not results:
            logger.warning(f"No matches for search: {name}")
            return {}

        valid_results = {}
        for entry in results:
            if entry and "title" in entry:
                title = entry["title"]
                url = entry.get("webpage_url", entry.get("url", ""))
                if url:
                    valid_results[title] = url

        logger.debug(f"Found {len(valid_results)} result(s) for '{name}'")
        return valid_results

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
        entries = await cls.__fetch_metadata(
            playlist_url, is_playlist=True, full_metadata=False
        )

        if not entries:
            logger.warning(f"Empty or invalid playlist: {playlist_url}")
            return

        logger.debug(f"Yielding {len(entries)} track(s) from playlist: {playlist_url}")
        for entry in entries:
            if entry and "url" in entry:
                url = entry["url"]
                if not url.startswith("http"):
                    url = f"https://www.youtube.com/watch?v={entry.get('id', entry['url'])}"
                logger.debug(f"Yielding track URL: {url}")
                yield url
