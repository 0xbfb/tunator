from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.repository import DatabaseRepository
from app.main import create_app


def _diagnostics_columns(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("PRAGMA table_info(diagnostics)").fetchall()
        return {str(row["name"]) for row in rows}
    finally:
        conn.close()


def test_init_db_migrates_legacy_diagnostics_schema(temp_paths: dict[str, Path]) -> None:
    db_path = temp_paths["db"]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                diagnostic_type TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT INTO diagnostics (diagnostic_type, result_json) VALUES (?, ?)",
            ("full", '[{"name":"service_running","ok":true,"details":"ok"}]'),
        )
        conn.commit()
    finally:
        conn.close()

    repo = DatabaseRepository(db_path=str(db_path))
    repo.init_db()

    columns = _diagnostics_columns(db_path)
    assert {"run_id", "source", "freshness", "checked_at"}.issubset(columns)

    latest = repo.fetch_latest_diagnostics()
    assert latest is not None
    assert latest["source"] == "manual"
    assert latest["freshness"] == "fresh"
    assert isinstance(latest["checks"], list)


def test_status_endpoint_with_legacy_db_still_returns_200(temp_paths: dict[str, Path]) -> None:
    db_path = temp_paths["db"]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                diagnostic_type TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    app = create_app()
    client = TestClient(app)
    response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.json()
    assert "latest_diagnostics" in payload
    assert payload["latest_diagnostics"] is None


def test_init_db_creates_expected_columns_for_new_database(temp_paths: dict[str, Path]) -> None:
    repo = DatabaseRepository(db_path=str(temp_paths["db"]))
    repo.init_db()
    columns = _diagnostics_columns(temp_paths["db"])
    assert {"run_id", "source", "freshness", "checked_at"}.issubset(columns)
