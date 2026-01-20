"""Logging configuration with colored output and file rotation."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from colorama import Fore, Style, init

init(autoreset=True)

COLORS: dict[str, str] = {
    "DEBUG": Fore.CYAN,
    "INFO": Fore.GREEN,
    "WARNING": Fore.YELLOW,
    "ERROR": Fore.RED,
    "CRITICAL": Fore.MAGENTA + Style.BRIGHT,
}

DEFAULT_LOG_LEVEL: str = "INFO"
BASE_LOG_FILE_NAME: str = "bot.log"


def setup_logger(
    name: str,
    log_level: str = DEFAULT_LOG_LEVEL,
    log_file: str | None = BASE_LOG_FILE_NAME,
) -> logging.Logger:
    """Logger with colored console output and rotating file handler"""

    logger = logging.getLogger(name)

    # Clear any existing handlers
    logger.handlers.clear()

    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    class ColorFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            if sys.stdout.isatty():  # Only color in terminal
                # Make a copy to avoid modifying the original record
                record = logging.makeLogRecord(record.__dict__)
                color = COLORS.get(record.levelname, "")
                record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"
                record.msg = f"{color}{record.msg}{Style.RESET_ALL}"
            return super().format(record)

    console_formatter = ColorFormatter(
        fmt="[%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler with rotation (10MB max, 3 backup files)
    if log_file:
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)

        log_file_path = log_dir / log_file
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(level)

        file_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger
