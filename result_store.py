from __future__ import annotations

import json
import threading
from collections import Counter
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
                file.write(f"{email_address}----{password}\n")

    def save_token_result(
        self,
        email: str,
        password: str,
        client_id: str,
        refresh_token: str,
        access_token: str,
        expire_at: float,
        domain: str,
    ) -> None:
        email_address = build_email_address(email, domain)
        with self._lock:
            with OUTLOOK_TOKEN_PATH.open("a", encoding="utf-8") as file:
                file.write(f"{email_address}----{password}----{client_id}----{refresh_token}\n")

    def save_task_result(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._append_jsonl(TASK_RESULTS_PATH, payload)

    def save_task_event(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._append_jsonl(TASK_EVENTS_PATH, payload)

    def get_dashboard_stats(self, recent_limit: int = 100) -> Dict[str, Any]:
        results: list[Dict[str, Any]] = []
        if TASK_RESULTS_PATH.exists():
            for line in TASK_RESULTS_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    results.append(payload)

        recent_results = results[-recent_limit:]
        total_recent = len(recent_results)
        register_success = sum(1 for item in recent_results if str(item.get("stage", "")) == "post_register" and bool(item.get("success")))
        oauth_success = sum(1 for item in recent_results if str(item.get("stage", "")) == "oauth" and bool(item.get("success")))
        avg_duration_ms = int(sum(int(item.get("duration_ms", 0) or 0) for item in recent_results) / total_recent) if total_recent else 0
        risk_count = sum(1 for item in recent_results if bool(item.get("risk_detected")))
        total_upload_bytes = sum(int(item.get("request_bytes", 0) or 0) for item in recent_results)
        total_download_bytes = sum(int(item.get("response_bytes", 0) or 0) for item in recent_results)
        total_blocked = sum(int(item.get("blocked_count", 0) or 0) for item in recent_results)
        avg_upload_bytes = int(total_upload_bytes / total_recent) if total_recent else 0
        avg_download_bytes = int(total_download_bytes / total_recent) if total_recent else 0
        avg_blocked = round(total_blocked / total_recent, 1) if total_recent else 0.0
        error_counter = Counter(
            str(item.get("error_code") or "UNKNOWN")
            for item in recent_results
            if not bool(item.get("success"))
        )

        return {
            "recent_total": total_recent,
            "register_success_rate": round((register_success / total_recent) * 100, 1) if total_recent else 0.0,
            "oauth_success_rate": round((oauth_success / total_recent) * 100, 1) if total_recent else 0.0,
            "avg_duration_ms": avg_duration_ms,
            "risk_count": risk_count,
            "total_upload_bytes": total_upload_bytes,
            "total_download_bytes": total_download_bytes,
            "avg_upload_bytes": avg_upload_bytes,
            "avg_download_bytes": avg_download_bytes,
            "total_blocked": total_blocked,
            "avg_blocked": avg_blocked,
            "error_distribution": dict(error_counter.most_common(8)),
        }
