"""
Utilities module for EMAIL SENDER.
Provides date-wise file logging configuration.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from config import Config


def setup_logger(name: str) -> logging.Logger:
    """
    Sets up a logger with a console handler and a date-wise file handler.
    
    Args:
        name: Name of the logger.
        
    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(Config.LOG_LEVEL)

    # Avoid duplicate handlers if already configured
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Date-wise File Handler
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_file = Config.LOGS_DIR / f"sender_{today_str}.log"
    
    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        # Fallback if log file cannot be created
        print(f"Warning: Could not create log file at {log_file}: {e}", file=sys.stderr)

    return logger
