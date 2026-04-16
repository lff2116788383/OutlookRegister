from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from app_config import CONFIG_PATH, OAUTH_TOKEN_ACCOUNTS_PATH, PENDING_OAUTH_ACCOUNTS_PATH, RESULTS_DIR


@dataclass(slots=True)
class ResultFileEntry:
    label: str
    path: Path


RESULT_FILES: List[ResultFileEntry] = [
    ResultFileEntry(label="待 OAuth2 邮箱账号", path=PENDING_OAUTH_ACCOUNTS_PATH),
    ResultFileEntry(label="OAuth2 Token 账号", path=OAUTH_TOKEN_ACCOUNTS_PATH),
]

DEFAULT_LOG_PATH = RESULTS_DIR / "app.log"
DEFAULT_CONFIG_PATH = CONFIG_PATH
