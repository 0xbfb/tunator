from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def record_config_change(self, changed_fields: dict[str, str], applied_successfully: bool, validation_errors: list[str]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO config_changes(changed_fields_json, applied_successfully, validation_errors_json) VALUES (?, ?, ?)",
                (json.dumps(changed_fields), int(applied_successfully), json.dumps(validation_errors)),
            )

    def record_diagnostics(self, diagnostic_type: str, result: list[dict[str, object]]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO diagnostics(diagnostic_type, result_json) VALUES (?, ?)",
                (diagnostic_type, json.dumps(result)),
            )
