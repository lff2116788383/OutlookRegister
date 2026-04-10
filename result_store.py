from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict

from app_config import LOGGED_EMAIL_PATH, OUTLOOK_TOKEN_PATH, RESULTS_DIR, UNLOGGED_EMAIL_PATH
from utils import build_email_address

TASK_RESULTS_PATH = RESULTS_DIR / "task_results.jsonl"
TASK_EVENTS_PATH = RESULTS_DIR / "task_events.jsonl"


class ResultStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _append_jsonl(self, path: Path, payload: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def save_registered_email(self, email: str, password: str, oauth_enabled: bool, domain: str) -> None:
        file_path = LOGGED_EMAIL_PATH if oauth_enabled else UNLOGGED_EMAIL_PATH
        email_address = build_email_address(email, domain)
        with self._lock:
            with file_path.open("a", encoding="utf-8") as file:
                file.write(f"{email_address}: {password}\n")

    def save_token_result(
        self,
        email: str,
        password: str,
        refresh_token: str,
        access_token: str,
        expire_at: float,
        domain: str,
    ) -> None:
        email_address = build_email_address(email, domain)
        with self._lock:
            with OUTLOOK_TOKEN_PATH.open("a", encoding="utf-8") as file:
                file.write(
                    f"{email_address}---{password}---{refresh_token}---{access_token}---{expire_at}\n"
                )

    def save_task_result(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._append_jsonl(TASK_RESULTS_PATH, payload)

    def save_task_event(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._append_jsonl(TASK_EVENTS_PATH, payload)
