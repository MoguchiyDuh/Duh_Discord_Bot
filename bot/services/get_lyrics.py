from dataclasses import dataclass
from typing import List, Optional

import aiohttp
from bs4 import BeautifulSoup

from bot.utils.config import GENIUS_API_KEY
from bot.utils.logger import BASE_LOG_FILE_NAME, setup_logger

logger = setup_logger(name="get_lyrics", log_to_file=True, log_file=BASE_LOG_FILE_NAME)


@dataclass
class Lyrics:
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

    url = f"https://api.genius.com/search?q={track_name}"
    headers = {"Authorization": f"Bearer {GENIUS_API_KEY}"}
    lyrics = Lyrics()

    async with aiohttp.ClientSession() as session:
        try:
            # Search for the track
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return Lyrics(status=response.status)
                data = await response.json()

            tracks = data.get("response", {}).get("hits", [])
            if not tracks:
                return Lyrics(status=404, error_message="Track not found.")

            # Extract track details
            track = tracks[0]["result"]
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
    chunks = []
    current_chunk = ""
    current_size = 0

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

    return chunks
