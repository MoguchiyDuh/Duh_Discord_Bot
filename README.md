# Duh Discord Bot

A multipurpose Discord bot with music, minigames, temporary voice channels, and weather features.

## Features

- **Music**: Play YouTube music with queue management, playlists, lyrics
- **Minigames**: Chess, Tic-Tac-Toe, Connect Four with interactive UI
- **Temporary Channels**: Auto-created voice channels with owner controls
- **Weather**: Current conditions using Open-Meteo API (no key required)
- **Utilities**: Server stats, ping, message clearing

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

## License

This project is open source. See individual dependencies for their licenses.
