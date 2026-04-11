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

    def _column_exists(self, connection: sqlite3.Connection, column_name: str) -> bool:
        rows = connection.execute("PRAGMA table_info(tasks)").fetchall()
        return any(str(row[1]) == column_name for row in rows)

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    password TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_code TEXT DEFAULT '',
                    error_message TEXT DEFAULT '',
                    stage TEXT DEFAULT '',
                    risk_detected INTEGER NOT NULL DEFAULT 0,
                    retry_mode TEXT NOT NULL DEFAULT 'full',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            if not self._column_exists(connection, "error_code"):
                connection.execute("ALTER TABLE tasks ADD COLUMN error_code TEXT DEFAULT ''")
            if not self._column_exists(connection, "error_message"):
                connection.execute("ALTER TABLE tasks ADD COLUMN error_message TEXT DEFAULT ''")
            if not self._column_exists(connection, "stage"):
                connection.execute("ALTER TABLE tasks ADD COLUMN stage TEXT DEFAULT ''")
            if not self._column_exists(connection, "risk_detected"):
                connection.execute("ALTER TABLE tasks ADD COLUMN risk_detected INTEGER NOT NULL DEFAULT 0")
            if not self._column_exists(connection, "retry_mode"):
                connection.execute("ALTER TABLE tasks ADD COLUMN retry_mode TEXT NOT NULL DEFAULT 'full'")
            connection.commit()

    def create_task(self, email: str, password: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO tasks (email, password, status, error_code, error_message, stage, risk_detected, retry_mode) VALUES (?, ?, 'pending', '', '', '', 0, 'full')",
                (email, password),
            )
            connection.commit()

    def get_pending_tasks(self, limit: int = 1) -> List[Tuple[int, str, str, str]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT id, email, password, retry_mode FROM tasks WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            for task_id, _, _, _ in rows:
                connection.execute(
                    "UPDATE tasks SET status = 'reserved', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (task_id,),
                )
            connection.commit()
            return [(int(task_id), str(email), str(password), str(retry_mode or 'full')) for task_id, email, password, retry_mode in rows]

    def update_task_status(
        self,
        task_id: int,
        status: str,
        error_message: str = "",
        error_code: str = "",
        stage: str = "",
        risk_detected: bool = False,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, error_code = ?, error_message = ?, stage = ?, risk_detected = ?, retry_mode = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    status,
                    error_code,
                    error_message,
                    stage,
                    int(risk_detected),
                    "oauth_only" if error_code == "OAUTH_FAILED" else "full",
                    task_id,
                ),
            )
            connection.commit()

    def reset_task_to_pending(self, task_id: int) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = 'pending', error_code = '', error_message = '', stage = '', risk_detected = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (task_id,),
            )
            connection.commit()

    def reset_failed_tasks_to_pending(self) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET status = 'pending', error_code = '', error_message = '', stage = '', risk_detected = 0, updated_at = CURRENT_TIMESTAMP
                WHERE status = 'failed'
                """
            )
            connection.commit()
            return int(cursor.rowcount or 0)

    def get_recent_failure_stats(self, limit: int = 20) -> Dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT error_code, COUNT(*)
                FROM (
                    SELECT error_code
                    FROM tasks
                    WHERE status = 'failed'
                    ORDER BY updated_at DESC
                    LIMIT ?
                )
                GROUP BY error_code
                """,
                (limit,),
            ).fetchall()
        return {str(error_code or "UNKNOWN"): int(count) for error_code, count in rows}

    def get_recent_tasks(self, limit: int = 30, status_filter: str = "all") -> List[Tuple[int, str, str, str, str, int, str]]:
        query = """
            SELECT id, email, status, stage, error_code, risk_detected, updated_at
            FROM tasks
        """
        params: list[object] = []
        if status_filter == "risk":
            query += " WHERE risk_detected = 1 "
        elif status_filter != "all":
            query += " WHERE status = ? "
            params.append(status_filter)
        query += " ORDER BY updated_at DESC, id DESC LIMIT ? "
        params.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            (
                int(task_id),
                str(email),
                str(status),
                str(stage or "-"),
                str(error_code or "-"),
                int(risk_detected),
                str(updated_at),
            )
            for task_id, email, status, stage, error_code, risk_detected, updated_at in rows
        ]

    def get_task_detail(self, task_id: int) -> Dict[str, str]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, email, status, stage, error_code, error_message, risk_detected, retry_mode, created_at, updated_at
                FROM tasks
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        if not row:
            return {}
        return {
            "id": str(row[0]),
            "email": str(row[1]),
            "status": str(row[2]),
            "stage": str(row[3] or "-"),
            "error_code": str(row[4] or "-"),
            "error_message": str(row[5] or "-"),
            "risk_detected": "是" if int(row[6]) else "否",
            "retry_mode": str(row[7] or "full"),
            "created_at": str(row[8]),
            "updated_at": str(row[9]),
        }

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
