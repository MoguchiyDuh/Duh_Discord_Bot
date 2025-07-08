<<<<<<< HEAD
<<<<<<< HEAD
from dataclasses import dataclass
from typing import List, Optional

import aiohttp
from bs4 import BeautifulSoup

from bot.utils.config import GENIUS_API_KEY
from bot.utils.logger import BASE_LOG_FILE_NAME, setup_logger

logger = setup_logger(name="get_lyrics", log_to_file=True, log_file=BASE_LOG_FILE_NAME)
=======
import aiohttp
from bot.utils.config import GENIUS_API_KEY
from bs4 import BeautifulSoup
from dataclasses import dataclass
>>>>>>> f5ed92a (logger, better code, fixes)


@dataclass
class Lyrics:
<<<<<<< HEAD
    status: Optional[int] = None
    title: Optional[str] = None
    text: Optional[list[str]] = None
    url: Optional[str] = None
    error_message: Optional[str] = None


async def get_lyrics(track_name: str) -> Lyrics:
    """Fetch lyrics from Genius API"""
    if not GENIUS_API_KEY:
        logger.error("No Genius API key found!")
        return Lyrics(status=500, error_message="No Genius API key found.")

=======
    status: int | None = None
    title: str | None = None
    text: list[str] | None = None
    url: str | None = None
    error_message: str | None = None


async def get_lyrics(track_name: str) -> Lyrics:
    if GENIUS_API_KEY is None:
        print("No Genius API key found!")
        return
>>>>>>> f5ed92a (logger, better code, fixes)
    url = f"https://api.genius.com/search?q={track_name}"
    headers = {"Authorization": f"Bearer {GENIUS_API_KEY}"}
    lyrics = Lyrics()

    async with aiohttp.ClientSession() as session:
        try:
            # Search for the track
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
<<<<<<< HEAD
                    return Lyrics(status=response.status)
                data = await response.json()

            tracks = data.get("response", {}).get("hits", [])
            if not tracks:
                return Lyrics(status=404, error_message="Track not found.")

            # Extract track details
            track = tracks[0]["result"]
=======
                    lyrics.status = response.status
                    return lyrics
                data = await response.json()

            track = data.get("response", {}).get("hits", [])
            if not track:
                lyrics.status = 404
                return lyrics

            # Extract track details
            track = track[0]["result"]
>>>>>>> f5ed92a (logger, better code, fixes)
            lyrics.status = 200
            lyrics.title = track["full_title"]
            lyrics.url = track["url"]

            # Fetch lyrics page
            async with session.get(lyrics.url) as response:
                if response.status != 200:
                    lyrics.status = response.status
                    return lyrics
                html = await response.text()

            # Parse HTML for lyrics
            soup = BeautifulSoup(html, "html.parser")
<<<<<<< HEAD
            lyrics_container = soup.find("div", id="lyrics-root")

            # Remove tags that are not lyrics
            tags_to_remove = lyrics_container.find_all(
                attrs={"data-exclude-from-selection": "true"}
            )
            for tag in tags_to_remove:
                tag.extract()
            footer_div = soup.find(
                "div", class_="LyricsFooter__Container-sc-bb41127e-0"
            )
            if footer_div:
                footer_div.extract()

            lyrics_text = lyrics_container.get_text(separator="\n", strip=True).replace(
                "[", "\n["
            )
            # Add full lyrics link and split into chunks
            lyrics_text += f"\n\n🔗 Full lyrics: {lyrics.url}"
            lyrics.text = split_track_into_chunks(lyrics_text)

        except aiohttp.ClientError as e:
            return Lyrics(status=500, error_message=f"Error fetching data: {str(e)}")

        logger.debug(lyrics)
        return lyrics


def split_track_into_chunks(strings: str, max_chunk_size: int = 4000) -> List[str]:
    """Split lyrics into chunks to fit within Discord's maximum symbol limit per message"""
    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size must be greater than 0.")

    # Step 1: Preprocess the input string to handle [markers]
    track_parts = []
    for track_part in strings.split("["):
        if not track_part.strip():
            continue  # Skip empty parts
        if "]" in track_part:
            track_part = "[" + track_part.strip()  # Re-add the opening bracket
        track_parts.append(track_part)

    # Step 2: Build chunks that respect the max_chunk_size
=======
            lyrics_divs = soup.find("div", id="lyrics-root").find_all(
                class_="Lyrics-sc-1bcc94c6-1 bzTABU"
            )
            if not lyrics_divs:
                lyrics.error_message = "Lyrics not found on page."
            else:
                # Get track parts for prettier splitting (ex. [Into], [Chorus])
                lyrics_divs_text = [
                    i.get_text(separator="\n", strip=True) for i in lyrics_divs
                ]
                lyrics_divs_text.append(f"\n🔗 Full lyrics: {lyrics.url}")
                chunks = split_track_into_chunks(lyrics_divs_text)
                lyrics.text = chunks

        except aiohttp.ClientError as e:
            lyrics.status = 500
            lyrics.error_message = f"Error fetching data: {str(e)}"

        return lyrics


def split_track_into_chunks(strings: list[str], max_chunk_size=4000) -> list[str]:

    track_parts = []
    for chunk in strings:
        for track_part in chunk.split("["):
            if not track_part:
                continue
            if "]" in track_part:
                track_part = "[" + track_part.strip()

            track_part = track_part
            track_parts.append(track_part)

>>>>>>> f5ed92a (logger, better code, fixes)
    chunks = []
    current_chunk = ""
    current_size = 0

<<<<<<< HEAD
    for part in track_parts:
        # Check if adding the next part exceeds the max_chunk_size
        if current_size + len(part) + 2 <= max_chunk_size:  # +2 accounts for "\n\n"
            current_chunk += part + "\n\n"
            current_size += len(part) + 2
        else:
            # Finalize the current chunk and start a new one
            chunks.append(current_chunk.strip())  # Strip trailing newlines
            current_chunk = part + "\n\n"
            current_size = len(part) + 2

    # Add any remaining content as the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
=======
    for string in track_parts:
        if current_size + len(string) <= max_chunk_size:
            current_chunk += string + "\n\n"
            current_size += len(string)
        else:
            chunks.append(current_chunk)
            current_chunk = string + "\n\n"
            current_size = len(string)

    if current_chunk:
        chunks.append(current_chunk)
>>>>>>> f5ed92a (logger, better code, fixes)

    return chunks
=======
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
    if not GENIUS_API_KEY:
        raise LyricsError("GENIUS_API_KEY is missing")

    search_url = f"https://api.genius.com/search?q={track_name}"
    headers = {"Authorization": f"Bearer {GENIUS_API_KEY}"}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(search_url, headers=headers) as res:
                if res.status != 200:
                    raise LyricsError(
                        f"Genius API search failed with status {res.status}"
                    )
                data = await res.json()

            hits = data.get("response", {}).get("hits", [])
            if not hits:
                raise LyricsError("Track not found in Genius search results")

            result = hits[0]["result"]
            lyrics_url = result["url"]

            async with session.get(lyrics_url) as res:
                if res.status != 200:
                    raise LyricsError(f"Failed to fetch lyrics page: HTTP {res.status}")
                html = await res.text()

            soup = BeautifulSoup(html, "html.parser")
            container = soup.find("div", id="lyrics-root")
            if not container:
                raise LyricsError("Lyrics container not found in HTML")

            for tag in container.find_all(
                attrs={"data-exclude-from-selection": "true"}
            ):
                tag.extract()
            footer = soup.find("div", class_="LyricsFooter__Container-sc-bb41127e-0")
            if footer:
                footer.extract()

            raw_text = container.get_text(separator="\n", strip=True).replace(
                "[", "\n["
            )
            raw_text += f"\n\n🔗 Lyrics page: {lyrics_url}"
            chunks = _split_lyrics_into_chunks(raw_text)

            artists = result["artist_names"]
            if type(artists) == list:
                artists = ", ".join(artists)

            return Lyrics(
                title=result["full_title"],
                artists=artists,
                text=chunks,
                url=lyrics_url,
            )

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
>>>>>>> 489c3f3 (changed to ffmpegOpus, added shuffle, skip, help commands, better playlist handling)
