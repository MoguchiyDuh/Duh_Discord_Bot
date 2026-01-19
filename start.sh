#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"
mkdir -p "$PID_DIR"

echo "Starting Duh Discord Bot..."

# Check if already running
if [ -f "$PID_DIR/bot.pid" ]; then
    BOT_PID=$(cat "$PID_DIR/bot.pid")
    if kill -0 "$BOT_PID" 2>/dev/null; then
        echo "Bot is already running (PID: $BOT_PID)"
        exit 1
    else
        rm "$PID_DIR/bot.pid"
    fi
fi

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "ERROR: uv is not installed"
    exit 1
fi

# Check .env
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "ERROR: .env file not found"
    exit 1
fi

cd "$SCRIPT_DIR"

# Start bot using managed execution
# uv run automatically handles environment sync and dependency resolution
echo "Starting bot..."
uv run python -m bot > "$SCRIPT_DIR/bot.log" 2>&1 &
echo $! > "$PID_DIR/bot.pid"

echo "Bot started (PID: $(cat "$PID_DIR/bot.pid"))"
echo "Log: $SCRIPT_DIR/bot.log"
echo "To stop: ./stop.sh"
