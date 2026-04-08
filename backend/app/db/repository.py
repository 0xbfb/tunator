from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)


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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
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
                    updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO service_runtime (id, status, phase, updated_at)
                VALUES (1, 'stopped', 'idle', CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO NOTHING
                """
            )
            self._run_schema_migrations(conn)

    def _run_schema_migrations(self, conn: sqlite3.Connection) -> None:
        self._ensure_columns(
            conn,
            "diagnostics",
            {
                "run_id": "TEXT",
                "source": "TEXT",
                "freshness": "TEXT",
                "checked_at": "TEXT",
            },
        )
        self._ensure_columns(
            conn,
            "service_runtime",
            {
                "run_id": "TEXT",
                "status": "TEXT",
                "phase": "TEXT",
                "pid": "INTEGER",
                "started_at": "TEXT",
                "last_seen_at": "TEXT",
                "last_error": "TEXT",
                "socks_port": "INTEGER",
                "control_port": "INTEGER",
                "updated_at": "TEXT",
            },
        )

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, expected: dict[str, str]) -> None:
        existing = self._table_columns(conn, table)
        if not existing:
            return
        for column, sql_type in expected.items():
            if column in existing:
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

    def record_config_change(self, changed_fields: dict[str, str], applied_successfully: bool, validation_errors: list[str]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO config_changes(changed_fields_json, applied_successfully, validation_errors_json) VALUES (?, ?, ?)",
                (json.dumps(changed_fields), int(applied_successfully), json.dumps(validation_errors)),
            )

    def record_diagnostics(
        self,
        diagnostic_type: str,
        result: list[dict[str, object]],
        run_id: str | None,
        source: str,
        freshness: str,
        checked_at: str,
    ) -> None:
        try:
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO diagnostics(diagnostic_type, result_json, run_id, source, freshness, checked_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (diagnostic_type, json.dumps(result), run_id, source, freshness, checked_at),
                )
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            logger.exception("Failed to persist diagnostics snapshot")

    def fetch_latest_diagnostics(self) -> dict[str, Any] | None:
        try:
            with self.connect() as conn:
                row = conn.execute(
                    """
                    SELECT result_json, run_id, source, freshness, checked_at
                    FROM diagnostics
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()
                if not row:
                    return None
                checks_payload = row["result_json"] or "[]"
                try:
                    checks = json.loads(checks_payload)
                except json.JSONDecodeError:
                    logger.exception("Invalid diagnostics payload in database")
                    checks = []
                return {
                    "checks": checks,
                    "run_id": row["run_id"],
                    "source": row["source"] or "manual",
                    "freshness": row["freshness"] or "fresh",
                    "checked_at": row["checked_at"],
                }
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            logger.exception("Failed to read latest diagnostics snapshot")
            return None

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
                    "updated_at": None,
                }
            return dict(row)
