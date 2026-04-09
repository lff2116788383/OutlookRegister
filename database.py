from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Tuple

from app_config import RESULTS_DIR, ensure_runtime_dirs

ensure_runtime_dirs()

DB_PATH = RESULTS_DIR / "tasks.db"


class TaskDB:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    password TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def create_task(self, email: str, password: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO tasks (email, password, status, error_message) VALUES (?, ?, 'pending', '')",
                (email, password),
            )
            connection.commit()

    def get_pending_tasks(self, limit: int = 1) -> List[Tuple[int, str, str]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT id, email, password FROM tasks WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            for task_id, _, _ in rows:
                connection.execute(
                    "UPDATE tasks SET status = 'reserved', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (task_id,),
                )
            connection.commit()
            return [(int(task_id), str(email), str(password)) for task_id, email, password in rows]

    def update_task_status(self, task_id: int, status: str, error_message: str = "") -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, error_message, task_id),
            )
            connection.commit()

    def reset_in_progress_tasks(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET status = 'pending', updated_at = CURRENT_TIMESTAMP WHERE status IN ('reserved', 'in_progress')"
            )
            connection.commit()

    def get_stats(self) -> Dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) FROM tasks GROUP BY status"
            ).fetchall()
        stats = {str(status): int(count) for status, count in rows}
        for status in ["pending", "reserved", "in_progress", "success", "failed"]:
            stats.setdefault(status, 0)
        return stats

    def clear_all_tasks(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM tasks")
            connection.commit()
