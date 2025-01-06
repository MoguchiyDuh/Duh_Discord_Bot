import logging
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
