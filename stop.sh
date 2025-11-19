#!/bin/bash

# Stop Duh Discord Bot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"

echo "Stopping Duh Discord Bot..."

# Stop bot
if [ -f "$PID_DIR/bot.pid" ]; then
    BOT_PID=$(cat "$PID_DIR/bot.pid")
    if kill -0 "$BOT_PID" 2>/dev/null; then
        echo "Stopping bot (PID: $BOT_PID)..."
        kill "$BOT_PID"
        rm "$PID_DIR/bot.pid"
        echo "Bot stopped"
    else
        echo "Bot not running"
        rm "$PID_DIR/bot.pid"
    fi
else
    echo "Bot PID file not found"
fi

echo "Duh Discord Bot stopped"
