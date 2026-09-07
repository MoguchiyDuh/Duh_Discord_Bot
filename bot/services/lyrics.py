from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import lyricsgenius

from bot.core.config import Settings

logger = logging.getLogger(__name__)


class LyricsError(Exception):
    pass


@dataclass(slots=True)
class Lyrics:
    title: str
    text: list[str]
    url: str


def split_track_query(query: str) -> tuple[str, str | None]:
    if " - " in query:
        artist, _, title = query.partition(" - ")
        return title.strip(), artist.strip()
    return query.strip(), None


def split_into_chunks(text: str, max_size: int = 4000) -> list[str]:
    lines: list[str] = []
    for raw in text.split("\n"):
        while len(raw) > max_size:
            lines.append(raw[:max_size])
            raw = raw[max_size:]
        lines.append(raw)

    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}{line}\n"
        if len(candidate) > max_size and current:
            chunks.append(current.rstrip())
            current = f"{line}\n"
        else:
            current = candidate
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


class LyricsService:
    def __init__(self, settings: Settings) -> None:
        if not settings.genius_api_key:
            self._client: lyricsgenius.Genius | None = None
            logger.warning("GENIUS_API_KEY not set, /lyrics is disabled")
        else:
            self._client = lyricsgenius.Genius(
                settings.genius_api_key,
                verbose=False,
                remove_section_headers=False,
                skip_non_songs=True,
                timeout=15,
            )

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def fetch(self, query: str) -> Lyrics:
        if self._client is None:
            raise LyricsError("GENIUS_API_KEY is not configured")

        title, artist = split_track_query(query)
        logger.debug("Fetching lyrics for %r by %r", title, artist)

        try:
            if artist:
                song = await asyncio.to_thread(self._client.search_song, title, artist)
            else:
                song = await asyncio.to_thread(self._client.search_song, title)
        except Exception as exc:
            logger.exception("Genius request failed for %r", query)
            raise LyricsError(f"lyrics request failed: {exc}") from exc

        if song is None:
            raise LyricsError("track not found on Genius")

        raw = song.lyrics or ""
        text = split_into_chunks(f"{raw}\n\n🔗 Lyrics page: {song.url}")
        return Lyrics(title=f"{song.artist} - {song.title}", text=text, url=song.url)
