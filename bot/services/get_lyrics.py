import json
from dataclasses import dataclass
from typing import List, Optional

import aiohttp
from bs4 import BeautifulSoup

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


async def get_lyrics(track_name: str) -> Lyrics:
    """Fetch lyrics from Genius for a given track name."""
    logger.debug(f"Fetching lyrics for: {track_name}")
    if not GENIUS_API_KEY:
        logger.error("GENIUS_API_KEY is missing")
        raise LyricsError("GENIUS_API_KEY is missing")

    search_url = f"https://api.genius.com/search?q={track_name}"
    headers = {"Authorization": f"Bearer {GENIUS_API_KEY}"}

    async with aiohttp.ClientSession() as session:
        try:
            logger.debug(f"Sending search request to Genius API: {search_url}")
            async with session.get(search_url, headers=headers) as res:
                logger.debug(f"Genius API responded with status {res.status}")
                if res.status != 200:
                    raise LyricsError(
                        f"Genius API search failed with status {res.status}"
                    )
                data = await res.json()

            hits = data.get("response", {}).get("hits", [])
            logger.debug(f"Received {len(hits)} search result(s) from Genius")

            if not hits:
                raise LyricsError("Track not found in Genius search results")

            result = hits[0]["result"]
            lyrics_url = result["url"]
            logger.debug(f"Lyrics page URL: {lyrics_url}")

            async with session.get(lyrics_url) as res:
                logger.debug(f"Fetching lyrics page, status: {res.status}")
                if res.status != 200:
                    raise LyricsError(f"Failed to fetch lyrics page: HTTP {res.status}")
                html = await res.text()

            soup = BeautifulSoup(html, "html.parser")
            container = soup.find("div", id="lyrics-root")
            if not container:
                logger.error("Lyrics container not found in HTML")
                raise LyricsError("Lyrics container not found in HTML")

            for tag in container.find_all(
                attrs={"data-exclude-from-selection": "true"}
            ):
                tag.extract()
            footer = soup.find("div", class_="LyricsFooter__Container-sc-bb41127e-0")
            if footer:
                footer.extract()

            logger.debug("Extracting and formatting lyrics text")
            raw_text = container.get_text(separator="\n", strip=True).replace(
                "[", "\n["
            )
            raw_text += f"\n\n🔗 Lyrics page: {lyrics_url}"
            chunks = _split_lyrics_into_chunks(raw_text)
            logger.debug(f"Lyrics split into {len(chunks)} chunk(s)")

            artists = result["artist_names"]
            if type(artists) == list:
                artists = ", ".join(artists)

            lyrics_obj = Lyrics(
                title=result["full_title"],
                artists=artists,
                text=chunks,
                url=lyrics_url,
            )
            logger.debug(
                f"Lyrics object created: {lyrics_obj.title} by {lyrics_obj.artists}"
            )
            return lyrics_obj

        except aiohttp.ClientError as e:
            logger.exception("Network error while fetching lyrics")
            raise LyricsError(f"Network failure: {e}") from e

        except Exception as e:
            logger.exception("Unexpected error during lyrics processing")
            raise LyricsError(f"Unexpected failure: {e}") from e


def _split_lyrics_into_chunks(text: str, max_chunk_size: int = 4000) -> List[str]:
    """Split lyrics into Discord-safe chunks."""
    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size must be > 0")

    parts = [
        f"[{part.strip()}" if "]" in part else part.strip()
        for part in text.split("[")
        if part.strip()
    ]

    chunks, current_chunk, size = [], "", 0
    for part in parts:
        length = len(part) + 2
        if size + length <= max_chunk_size:
            current_chunk += part + "\n\n"
            size += length
        else:
            chunks.append(current_chunk.strip())
            current_chunk = part + "\n\n"
            size = length

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks
