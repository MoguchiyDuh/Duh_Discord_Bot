<<<<<<< HEAD
import os
<<<<<<< HEAD

=======
>>>>>>> f5ed92a (logger, better code, fixes)
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GENIUS_API_KEY = os.environ.get("GENIUS_API_KEY")
=======
import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GENIUS_API_KEY = os.environ.get("GENIUS_API_KEY")
>>>>>>> 489c3f3 (changed to ffmpegOpus, added shuffle, skip, help commands, better playlist handling)
