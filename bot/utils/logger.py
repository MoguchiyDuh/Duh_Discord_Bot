import logging
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
