import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set")
GENIUS_API_KEY = os.environ.get("GENIUS_API_KEY")
if not GENIUS_API_KEY:
    raise ValueError("GENIUS_API_KEY environment variable is not set")
