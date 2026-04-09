from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app_config import RESULTS_DIR, ensure_runtime_dirs

ensure_runtime_dirs()

logger = logging.getLogger("outlook_register")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        RESULTS_DIR / "app.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
