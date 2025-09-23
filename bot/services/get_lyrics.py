import asyncio
from dataclasses import dataclass
from functools import partial
from typing import List, Optional

import lyricsgenius

from bot.utils.config import GENIUS_API_KEY
from bot.utils.logger import setup_logger

logger = setup_logger(name="get_lyrics", log_file="lyrics.log")


class LyricsError(Exception):
    """Raised when lyrics fetching or parsing fails."""


@dataclass
class Lyrics:
    title: Optional[str] = None
    artists: Optional[str] = None
    text: Optional[List[str]] = None
    url: Optional[str] = None


def _split_lyrics_into_chunks(text: str, max_chunk_size: int = 4000) -> List[str]:
    """Split lyrics into Discord-safe chunks."""
    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size must be > 0")

    lines = text.split("\n")
    chunks, current_chunk, current_size = [], "", 0

    for line in lines:
        line_length = len(line) + 1

        if current_size + line_length <= max_chunk_size:
            current_chunk += line + "\n"
            current_size += line_length
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = line + "\n"
            current_size = line_length

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


async def get_lyrics(track_name: str, artist_name: Optional[str] = None) -> Lyrics:
    """Advanced version with artist name and better error handling."""
    logger.debug(f"Fetching lyrics for: {track_name} by {artist_name or 'any artist'}")

    if not GENIUS_API_KEY:
        logger.error("GENIUS_API_KEY is missing")
        raise LyricsError("GENIUS_API_KEY is missing")

    try:
        genius = lyricsgenius.Genius(
            GENIUS_API_KEY,
            verbose=False,
            remove_section_headers=False,
            skip_non_songs=True,
            timeout=15,
        )

        loop = asyncio.get_event_loop()

        if artist_name:
            logger.debug(f"Searching for {track_name} by {artist_name}")
            song = await loop.run_in_executor(
                None, partial(genius.search_song, track_name, artist_name)
            )
        else:
            logger.debug(f"Searching for: {track_name}")
            song = await loop.run_in_executor(
                None, partial(genius.search_song, track_name)
            )

        if not song:
            logger.error(f"No results found for: {track_name}")
            raise LyricsError("Track not found in Genius search results")

        logger.debug(f"Found song: {song.title} by {song.artist}")

        raw_lyrics = song.lyrics or ""
        final_text = f"{raw_lyrics}\n\n🔗 Lyrics page: {song.url}"
        chunks = _split_lyrics_into_chunks(final_text)

        lyrics_obj = Lyrics(
            title=f"{song.artist} - {song.title}",
            artists=song.artist,
            text=chunks,
            url=song.url,
        )

        return lyrics_obj

    except Exception as e:
        logger.exception(f"Error in advanced lyrics fetch: {e}")
        raise LyricsError(f"Failed to fetch lyrics: {e}") from e
