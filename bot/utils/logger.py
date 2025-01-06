import logging
<<<<<<< HEAD
import sys
from logging.handlers import RotatingFileHandler
from typing import Literal, Optional

DEFAULT_LOG_LEVEL = "DEBUG"


def setup_logger(
    name: str,
    log_level: Literal[
        "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
    ] = DEFAULT_LOG_LEVEL,
    log_to_file: bool = True,
    log_file: Optional[str] = "bot.log",
):

    log_levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    level = log_levels.get(log_level.upper(), logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    format = "[%(levelname)s] %(asctime)s - %(name)s: %(message)s"
    formatter = logging.Formatter(format)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.stream.reconfigure(encoding="utf-8")
    logger.addHandler(console_handler)

    if log_to_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


BASE_LOG_FILE_NAME = "bot.log"
=======
from logging.handlers import RotatingFileHandler


def setup_logger(
    log_file="bot.log", level=logging.DEBUG, max_bytes=5 * 1024 * 1024, backup_count=3
):
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.hasHandlers():
        return root_logger

    formatter = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    # %(asctime)s , datefmt="%Y-%m-%d %H:%M:%S"

    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


setup_logger()
bot_logger = logging.getLogger("discord_bot")
bot_logger.setLevel(logging.DEBUG)
discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.INFO)
yt_source_logger = logging.getLogger("youtube_source")
yt_source_logger.setLevel(logging.INFO)
>>>>>>> f5ed92a (logger, better code, fixes)
