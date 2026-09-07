from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from yt_dlp import YoutubeDL

from bot.core.config import Settings

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class YouTubeError(Exception):
    pass


@dataclass(slots=True)
class Track:
    page_url: str
    title: str
    duration: int | None = None
    thumbnail: str | None = None
    author: str | None = None
    author_url: str | None = None
    requester: str | None = None

    @property
    def formatted_duration(self) -> str | None:
        if self.duration is None:
            return None
        minutes, seconds = divmod(self.duration, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02}:{seconds:02}"
        return f"{minutes}:{seconds:02}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_url": self.page_url,
            "title": self.title,
            "duration": self.duration,
            "thumbnail": self.thumbnail,
            "author": self.author,
            "author_url": self.author_url,
            "requester": self.requester,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Track:
        return cls(
            page_url=data["page_url"],
            title=data["title"],
            duration=data.get("duration"),
            thumbnail=data.get("thumbnail"),
            author=data.get("author"),
            author_url=data.get("author_url"),
            requester=data.get("requester"),
        )


class YouTube:
    def __init__(self, settings: Settings) -> None:
        self._cookies_path = settings.cookies_path
        self._max_search = settings.max_search_results
        self._max_playlist = settings.max_playlist_fetch
        self._semaphore = asyncio.Semaphore(1)
        self._base_options: dict[str, Any] = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": 10,
            "noplaylist": True,
            "http_headers": {"User-Agent": _USER_AGENT},
        }
        if settings.pot_provider_url:
            self._base_options["extractor_args"] = {
                "youtubepot-bgutilhttp": {"base_url": [settings.pot_provider_url]},
            }
            logger.info("PO token provider: %s", settings.pot_provider_url)
        else:
            logger.warning("POT_PROVIDER_URL not set, relying on tokenless clients")

    def _options(self, *, flat: bool, playlist: bool) -> dict[str, Any]:
        options = self._base_options.copy()
        if playlist:
            options["noplaylist"] = False
            options["playlistend"] = self._max_playlist
        if flat:
            options["extract_flat"] = True
        if self._cookies_path.is_file() and self._cookies_path.stat().st_size > 0:
            options["cookiefile"] = str(self._cookies_path)
        return options

    async def _extract(self, query: str, *, flat: bool, playlist: bool) -> list[dict[str, Any]]:
        options = self._options(flat=flat, playlist=playlist)

        def _run() -> list[dict[str, Any]]:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(query, download=False)
            if not info:
                return []
            if "entries" in info:
                return [entry for entry in info["entries"] if entry is not None]
            return [info]

        try:
            async with self._semaphore:
                result = await asyncio.to_thread(_run)
        except Exception as exc:
            logger.error("yt-dlp failed for %r: %s", query, exc)
            raise YouTubeError(f"extraction failed: {exc}") from exc
        logger.debug("Extracted %d entries for %r", len(result), query)
        return result

    @staticmethod
    def _from_flat(entry: dict[str, Any]) -> Track | None:
        url = entry.get("url") or entry.get("webpage_url") or ""
        if not url.startswith("http"):
            video_id = entry.get("id")
            if not video_id:
                return None
            url = f"https://www.youtube.com/watch?v={video_id}"
        duration = entry.get("duration")
        try:
            duration = int(float(duration)) if duration else None
        except (TypeError, ValueError):
            duration = None
        return Track(
            page_url=url,
            title=entry.get("title") or "Unknown Title",
            duration=duration,
        )

    @staticmethod
    def _from_full(data: dict[str, Any]) -> Track:
        if uid := data.get("uploader_id"):
            author_url = f"https://youtube.com/channel/{uid}"
        else:
            author_url = data.get("channel_url") or data.get("uploader_url")
        duration = data.get("duration")
        try:
            duration = int(float(duration)) if duration else None
        except (TypeError, ValueError):
            duration = None
        return Track(
            page_url=data.get("webpage_url") or data.get("original_url") or "",
            title=data.get("title") or "Unknown Title",
            duration=duration,
            thumbnail=data.get("thumbnail"),
            author=data.get("uploader") or data.get("channel"),
            author_url=author_url,
        )

    async def search(self, query: str) -> list[Track]:
        entries = await self._extract(
            f"ytsearch{self._max_search}:{query}",
            flat=True,
            playlist=False,
        )
        tracks = [track for entry in entries if (track := self._from_flat(entry))]
        logger.debug("Search %r -> %d results", query, len(tracks))
        return tracks

    async def playlist(self, url: str) -> list[Track]:
        entries = await self._extract(url, flat=True, playlist=True)
        tracks = [track for entry in entries if (track := self._from_flat(entry))]
        logger.info("Playlist %r -> %d tracks", url, len(tracks))
        return tracks

    async def track(self, url: str) -> Track:
        entries = await self._extract(url, flat=False, playlist=False)
        if not entries:
            raise YouTubeError("no metadata returned")
        data = entries[0]
        if data.get("is_unavailable"):
            raise YouTubeError("track is unavailable")
        return self._from_full(data)

    async def stream_url(self, page_url: str) -> str:
        entries = await self._extract(page_url, flat=False, playlist=False)
        if not entries:
            raise YouTubeError("no stream returned")
        data = entries[0]
        audio_url = data.get("url") or ""
        if not audio_url:
            formats = [f for f in data.get("formats", []) if f.get("acodec") != "none"]
            if formats:
                audio_url = formats[-1].get("url", "")
        if not audio_url:
            raise YouTubeError("no audio format found")
        return audio_url
