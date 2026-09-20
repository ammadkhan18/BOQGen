from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterable

from models.schemas import ConfidenceLevel, Estimate

_RANK = {ConfidenceLevel.HIGH: 3, ConfidenceLevel.MEDIUM: 2, ConfidenceLevel.LOW: 1}


def combine_confidence(*estimates: Estimate) -> ConfidenceLevel:
    """A calculated quantity is only as trustworthy as its weakest input.

    Returns the LOWEST confidence level among the given Estimates (i.e. the
    most conservative reading), so a quantity built from one High- and one
    Low-confidence input is itself reported as Low confidence.
    """
    if not estimates:
        return ConfidenceLevel.MEDIUM
    worst = min(estimates, key=lambda e: _RANK[e.confidence])
    return worst.confidence


def round_up(value: float, digits: int = 2) -> float:
    return round(value + 1e-9, digits)


def format_currency(value: float, symbol: str = "\u20b9") -> str:
    return f"{symbol}{value:,.2f}"


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    return numerator / denominator if denominator else default


# --------------------------------------------------------------------------
# Optional local persistence (SQLite). Disabled by default in the UI since
# Streamlit Community Cloud has an ephemeral filesystem (data is wiped on
# every redeploy/restart) - but useful for local runs / self-hosting.
# --------------------------------------------------------------------------

DB_PATH = "project_history.db"


@contextmanager
def get_db_connection(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                created_at TEXT,
                grand_total REAL,
                currency TEXT,
                result_json TEXT
            )
            """
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_project_run(project_name: str, created_at: str, grand_total: float, currency: str, result_json: str, db_path: str = DB_PATH) -> None:
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO project_runs (project_name, created_at, grand_total, currency, result_json) VALUES (?, ?, ?, ?, ?)",
            (project_name, created_at, grand_total, currency, result_json),
        )


def list_project_runs(db_path: str = DB_PATH) -> Iterable[sqlite3.Row]:
    with get_db_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT id, project_name, created_at, grand_total, currency FROM project_runs ORDER BY id DESC LIMIT 50")
        return cur.fetchall()
