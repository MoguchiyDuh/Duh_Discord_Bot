#!/bin/bash

# Start Duh Discord Bot

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

# Check Python version
if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    echo "ERROR: Python 3.8+ required"
    exit 1
fi

# Create venv if needed
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/.venv"
fi

# Activate venv and install dependencies
cd "$SCRIPT_DIR"
source .venv/bin/activate
pip install -r requirements.txt --quiet 2>/dev/null

# Check .env
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "ERROR: .env file not found"
    exit 1
fi

# Start bot
echo "Starting bot..."
python3 -m bot > "$SCRIPT_DIR/bot.log" 2>&1 &
echo $! > "$PID_DIR/bot.pid"
echo "Bot started (PID: $(cat $PID_DIR/bot.pid))"

echo ""
echo "Duh Discord Bot is running!"
echo ""
echo "Log: $SCRIPT_DIR/bot.log"
echo ""
echo "To stop: ./stop.sh"
