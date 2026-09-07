# Duh Discord Bot

Multipurpose Discord bot: YouTube music with queue management, minigames (Chess, Tic-Tac-Toe, Connect Four), auto-managed temporary voice channels, weather, and random utilities.

Slash commands only.

## Features

- **Music**: YouTube playback with queue, playlists, search, lyrics, loop (track/queue), play-next, and a persistent player card — a single interactive message with two pages (now playing with progress bar, queue) and buttons for everything: prev/pause/skip, loop, shuffle, add song, volume, lyrics, stop. The card edits in place, shows a log of recent actions, and becomes a session-stats summary when playback ends. Volume is displayed 0-150% with 100% mapped to 30% raw gain (default 100%). Stream URLs are resolved at play time, so long queues never expire.
- **Queue persistence**: queues (and loop mode, volume) survive bot restarts, `/music leave`, and idle disconnects. A dead card from a previous session is replaced with an ended marker on the next session.
- **PO Token provider**: ships with a `bgutil-ytdlp-pot-provider` sidecar so YouTube extraction keeps working from VPS IPs.
- **Minigames**: Chess, Tic-Tac-Toe, Connect Four in private threads.
- **Temporary channels**: "Join to Create" voice hub with owner controls (lock, limit, rename, kick, mute).
- **Weather**: current conditions via Open-Meteo (no API key).
- **Utilities**: dice, coinflip, password generator, colors, lorem ipsum, server stats.

## Quick start

```bash
git clone https://github.com/MoguchiyDuh/Duh_Discord_Bot.git
cd Duh_Discord_Bot
cp .env.example .env
```

Fill in `DISCORD_TOKEN` in `.env`, then:

```bash
docker compose up -d --build
```

The bot creates a `Commands` category with its command channels (`🛠️┃bot-commands`, `🎮┃minigames`, `🎤┃media-hub`) and a `Temporary Channels` category with the `Join to Create` voice hub on join. Slash commands only work in those channels.

Optional:

- `GENIUS_API_KEY` ([genius.com/api-clients](https://genius.com/api-clients)) — enables `/music lyrics`.
- `SYNC_GUILD_ID` — instant guild-scoped command sync for development instead of global sync.
- Cookies: `mkdir -p data && touch data/cookies.txt` and paste Netscape-format cookies for age-restricted / members-only videos. The container runs as UID 1000 — `chown 1000:1000 data` if it's a bind mount.
- Logs land in `data/logs/bot.log` (rotating, 3 x 10 MB).

## Local development (no Docker)

```bash
uv sync
uv run python -m bot
```

Without `POT_PROVIDER_URL` set, yt-dlp falls back to tokenless clients — fine for testing, unreliable on datacenter IPs.

## Stack

- Python 3.13, discord.py 2.7, yt-dlp, uv
- FFmpeg + Cairo (chess board rendering) in the image
- Non-root container, `restart: unless-stopped`
