#!/bin/bash

# Change to the directory where this script is located
cd "$(dirname "$0")"

echo "Starting Duh Discord Bot..."
echo "Current directory: $(pwd)"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.8+ using your package manager"
    exit 1
fi

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 8) else 1)'; then
    echo "ERROR: Python 3.8+ required, found $python_version"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment"
        exit 1
    fi
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install/update dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "Installing/updating dependencies..."
    pip install -r requirements.txt --quiet
else
    echo "WARNING: requirements.txt not found, skipping dependency installation"
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found"
    echo "Please create a .env file with your DISCORD_TOKEN and GENIUS_API_KEY"
    exit 1
fi

echo
echo "Starting bot..."
echo "Press Ctrl+C to stop the bot"
echo

# Run the bot
python3 -m bot

# Check exit code
if [ $? -ne 0 ]; then
    echo
    echo "Bot stopped with error code $?"
    read -p "Press Enter to exit..."
fi