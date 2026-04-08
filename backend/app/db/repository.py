from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass(slots=True)
class DatabaseRepository:
    db_path: str

    @classmethod
    def from_env(cls) -> "DatabaseRepository":
        db_path = os.getenv("TUNATOR_DB_PATH", str(Path("./tunator.db").resolve()))
        repo = cls(db_path=db_path)
        repo.init_db()
        return repo

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS config_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    changed_fields_json TEXT NOT NULL,
                    applied_successfully INTEGER NOT NULL,
                    validation_errors_json TEXT,
                    warnings_json TEXT,
                    before_raw TEXT,
                    after_raw TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_column(conn, "config_changes", "warnings_json", "TEXT")
            self._ensure_column(conn, "config_changes", "before_raw", "TEXT")
            self._ensure_column(conn, "config_changes", "after_raw", "TEXT")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS diagnostics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    diagnostic_type TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    run_id TEXT,
                    source TEXT,
                    freshness TEXT,
                    checked_at TEXT,
                    summary TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_column(conn, "diagnostics", "summary", "TEXT")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS service_runtime (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    run_id TEXT,
                    status TEXT,
                    phase TEXT,
                    pid INTEGER,
                    started_at TEXT,
                    last_seen_at TEXT,
                    last_error TEXT,
                    socks_port INTEGER,
                    control_port INTEGER,
                    managed_by_tunator INTEGER DEFAULT 0,
                    last_action TEXT,
                    last_action_message TEXT,
                    updated_at TEXT
                )
                """
            )
            self._ensure_column(conn, "service_runtime", "managed_by_tunator", "INTEGER DEFAULT 0")
            self._ensure_column(conn, "service_runtime", "last_action", "TEXT")
            self._ensure_column(conn, "service_runtime", "last_action_message", "TEXT")

            conn.execute(
                """
                INSERT INTO service_runtime (id, status, phase, updated_at)
                VALUES (1, 'stopped', 'idle', CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO NOTHING
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS service_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    phase TEXT,
                    pid INTEGER,
                    message TEXT,
                    details_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS config_backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_path TEXT NOT NULL,
                    checksum TEXT,
                    size_bytes INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        row = conn.execute(f"PRAGMA table_info({table})").fetchall()
        columns = {item["name"] for item in row}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def record_config_change(
        self,
        changed_fields: dict[str, str],
        applied_successfully: bool,
        validation_errors: list[str],
        warnings: list[str] | None = None,
        before_raw: str | None = None,
        after_raw: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO config_changes(
                    changed_fields_json, applied_successfully, validation_errors_json, warnings_json, before_raw, after_raw
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    json.dumps(changed_fields),
                    int(applied_successfully),
                    json.dumps(validation_errors),
                    json.dumps(warnings or []),
                    before_raw,
                    after_raw,
                ),
            )

    def list_config_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, changed_fields_json, applied_successfully, validation_errors_json, warnings_json, created_at
                FROM config_changes
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            items = []
            for row in rows:
                items.append(
                    {
                        "id": row["id"],
                        "changed_fields": json.loads(row["changed_fields_json"]),
                        "applied_successfully": bool(row["applied_successfully"]),
                        "validation_errors": json.loads(row["validation_errors_json"] or "[]"),
                        "warnings": json.loads(row["warnings_json"] or "[]"),
                        "created_at": row["created_at"],
                    }
                )
            return items

    def record_backup(self, backup_path: str, checksum: str | None, size_bytes: int | None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO config_backups(backup_path, checksum, size_bytes) VALUES (?, ?, ?)",
                (backup_path, checksum, size_bytes),
            )

    def list_backups(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, backup_path, checksum, size_bytes, created_at
                FROM config_backups
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def record_diagnostics(
        self,
        diagnostic_type: str,
        result: list[dict[str, object]],
        run_id: str | None,
        source: str,
        freshness: str,
        checked_at: str,
        summary: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO diagnostics(diagnostic_type, result_json, run_id, source, freshness, checked_at, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (diagnostic_type, json.dumps(result), run_id, source, freshness, checked_at, summary),
            )

    def fetch_latest_diagnostics(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT result_json, run_id, source, freshness, checked_at, summary
                FROM diagnostics
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            return {
                "checks": json.loads(row["result_json"]),
                "run_id": row["run_id"],
                "source": row["source"] or "manual",
                "freshness": row["freshness"] or "fresh",
                "checked_at": row["checked_at"],
                "summary": row["summary"],
            }

    def update_runtime(self, values: dict[str, Any]) -> None:
        if not values:
            return
        columns = ", ".join(f"{key} = ?" for key in values.keys())
        params = list(values.values())
        with self.connect() as conn:
            conn.execute(f"UPDATE service_runtime SET {columns} WHERE id = 1", params)

    def fetch_runtime(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM service_runtime WHERE id = 1").fetchone()
            if not row:
                return {
                    "run_id": None,
                    "status": "stopped",
                    "phase": "idle",
                    "pid": None,
                    "started_at": None,
                    "last_seen_at": None,
                    "last_error": None,
                    "socks_port": None,
                    "control_port": None,
                    "managed_by_tunator": 0,
                    "last_action": None,
                    "last_action_message": None,
                    "updated_at": None,
                }
            return dict(row)

    def record_service_event(
        self,
        run_id: str | None,
        action: str,
        status: str,
        phase: str | None,
        pid: int | None,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO service_events(run_id, action, status, phase, pid, message, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, action, status, phase, pid, message, json.dumps(details or {})),
            )

    def list_service_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, run_id, action, status, phase, pid, message, details_json, created_at
                FROM service_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "action": row["action"],
                    "status": row["status"],
                    "phase": row["phase"],
                    "pid": row["pid"],
                    "message": row["message"],
                    "details": json.loads(row["details_json"] or "{}"),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
