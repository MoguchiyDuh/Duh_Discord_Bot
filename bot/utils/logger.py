import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Literal, Optional

DEFAULT_LOG_LEVEL = "INFO"
BASE_LOG_FILE_NAME = "bot.log"


def _get_log_level(
    level_name: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
) -> int:
    """Helper function to convert log level name to logging level constant."""
    log_levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return log_levels.get(level_name.upper(), logging.INFO)


def _create_handler(
    handler_class,
    level: int,
    formatter: logging.Formatter = logging.Formatter(
        "[%(levelname)s] %(asctime)s - %(name)s: %(message)s"
    ),
    **kwargs
):
    """Helper function to create and configure a handler."""
    handler = handler_class(**kwargs)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    if hasattr(handler, "stream") and hasattr(handler.stream, "reconfigure"):
        handler.stream.reconfigure(encoding="utf-8")
    return handler


def setup_logger(
    name: str,
    log_level: Literal[
        "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
    ] = DEFAULT_LOG_LEVEL,
    log_file: Optional[str] = BASE_LOG_FILE_NAME,
) -> logging.Logger:
    """Set up a logger with the specified name, level, and optional file output."""
    level = _get_log_level(log_level)
    logger = logging.getLogger(name)
    logger.setLevel(level)

    logger.handlers.clear()

    console_handler = _create_handler(logging.StreamHandler, level, stream=sys.stdout)
    logger.addHandler(console_handler)

    if log_file and not any(
        isinstance(h, RotatingFileHandler) for h in logger.handlers
    ):
        file_handler = _create_handler(
            RotatingFileHandler,
            level,
            filename=log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=3,
            encoding="utf-8",
        )
        logger.addHandler(file_handler)

    logger.propagate = False

    return logger
