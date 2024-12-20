import aiohttp
from .config import GENIUS_API_KEY
from bs4 import BeautifulSoup
from dataclasses import dataclass


@dataclass
class Lyrics:
    status: int = 0
    title: str = ""
    text: str = ""
    url: str = ""
    error_message: str = ""


async def get_lyrics(track_name: str) -> Lyrics:
    url = f"https://api.genius.com/search?q={track_name}"
    headers = {"Authorization": f"Bearer {GENIUS_API_KEY}"}
    lyrics = Lyrics()

    async with aiohttp.ClientSession() as session:
        try:
            # Search for the track
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    lyrics.status = response.status
                    return lyrics
                data = await response.json()

            track = data.get("response", {}).get("hits", [])
            if not track:
                lyrics.status = 404
                return lyrics

            # Extract track details
            track = track[0]["result"]
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
            lyrics_div = soup.find("div", {"data-lyrics-container": "true"})
            if lyrics_div is None:
                lyrics.error_message = "Lyrics not found on page."
            else:
                lyrics.text = (
                    lyrics_div.get_text(separator="\n").strip().replace("[", "\n[")
                )
                if len(lyrics.text) > 2000:
                    lyrics.text = lyrics.text[:1950] + "..."

        except aiohttp.ClientError as e:
            lyrics.status = 500
            lyrics.error_message = f"Error fetching data: {str(e)}"

        return lyrics
