"""Configuration settings loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str | None = os.environ.get("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set")

GENIUS_API_KEY: str | None = os.environ.get("GENIUS_API_KEY")

MAX_QUEUE_LENGTH: int = 50  # Limit for Discord bot queue
MAX_PLAYLIST_FETCH: int = 500  # Limit for yt-dlp playlist metadata fetching
