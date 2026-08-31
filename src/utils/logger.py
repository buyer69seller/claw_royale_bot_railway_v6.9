# src/utils/logger.py
"""Logging setup untuk bot"""

import logging
import sys
from pathlib import Path

from ..core.constants import LOG_DIR

def setup_logging(level=logging.INFO):
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console.setFormatter(console_format)
    root_logger.addHandler(console)
    
    log_file = Path(LOG_DIR) / "bot.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)
    
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    
    return root_logger