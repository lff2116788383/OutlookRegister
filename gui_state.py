from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from app_config import CONFIG_PATH, LOGGED_EMAIL_PATH, OUTLOOK_TOKEN_PATH, RESULTS_DIR, UNLOGGED_EMAIL_PATH


@dataclass(slots=True)
class ResultFileEntry:
    label: str
    path: Path


RESULT_FILES: List[ResultFileEntry] = [
    ResultFileEntry(label="已记录邮箱", path=LOGGED_EMAIL_PATH),
    ResultFileEntry(label="未初始化邮箱", path=UNLOGGED_EMAIL_PATH),
    ResultFileEntry(label="OAuth2 Token", path=OUTLOOK_TOKEN_PATH),
]

DEFAULT_LOG_PATH = RESULTS_DIR / "app.log"
DEFAULT_CONFIG_PATH = CONFIG_PATH
