# Duh Discord Bot

A multipurpose Discord bot with music, minigames, temporary voice channels, and weather features.

## Features

- **Music**: Play YouTube music with queue management, playlists, lyrics
- **Minigames**: Chess, Tic-Tac-Toe, Connect Four with interactive UI
- **Temporary Channels**: Auto-created voice channels with owner controls
- **Weather**: Current conditions using Open-Meteo API (no key required)
- **Utilities**: Server stats, ping, message clearing
- **MCP Integration**: Control bot music features via Claude Code MCP server (mcp_integration branch)

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/MoguchiyDuh/Duh_Discord_Bot.git
   cd Duh_Discord_Bot
   ```

2. **Configure environment**
  create
   ```.env
   DISCORD_TOKEN=<token>
   GENIUS_API_KEY=<api key>
   ```

4. **Run the bot**
   - **Windows**: Double-click `start.bat`
   - **Linux/macOS**: `./start.sh`

## Required Tokens

- **Discord Bot Token**: Get from [Discord Developer Portal](https://discord.com/developers/applications)
- **Genius API Key**: Get from [Genius API](https://genius.com/api-clients) (for lyrics)

## Commands

Commands are restricted to specific channels that the bot creates. All commands can be seen via "/help" (ViP)

## Requirements

- Python 3.8+
- FFmpeg (for music functionality)
- Cairo libraries (for chess board rendering)

## Installation Notes

The startup scripts handle virtual environment setup and dependency installation automatically. All required Python packages are listed in `requirements.txt`.

## MCP Integration (mcp_integration branch)

This branch includes an HTTP API server for external control via Model Context Protocol (MCP).

### Setup

1. **Bot runs API server on `http://127.0.0.1:8765` automatically**

2. **Configure MCP server in Claude Code** (`~/.claude.json`):
   ```json
   {
     "discord-bot": {
       "type": "stdio",
       "command": "/path/to/venv/bin/python",
       "args": ["/path/to/discord-bot-mcp/server.py"]
     }
   }
   ```

3. **Install MCP dependencies**:
   ```bash
   pip install httpx mcp
   ```

### Available MCP Tools

- `list_guilds` - List all Discord servers
- `get_player_status` - Get current player status, queue, and track info
- `search_music` - Search YouTube for tracks
- `add_to_queue` - Add tracks by URL or search query
- `skip_track` - Skip current or specific track by index
- `clear_queue` - Clear all queued tracks
- `pause_playback` / `resume_playback` - Control playback
- `shuffle_queue` - Shuffle the queue

### Usage Example

```python
# From Claude Code with MCP enabled
# Search for music
search_music(guild_id="123456", query="lofi hip hop")

# Add to queue
add_to_queue(guild_id="123456", url="https://youtube.com/watch?v=...")

# Check status
get_player_status(guild_id="123456")
```

## License

This project is open source. See individual dependencies for their licenses.
