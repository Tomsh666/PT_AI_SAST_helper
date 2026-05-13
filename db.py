"""Работа с SQLite-базой данных.

Пока одна таблица — findings. Остальные добавим по мере реализации шагов.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id  TEXT PRIMARY KEY,
    rule_id     TEXT NOT NULL,
    file_uri    TEXT NOT NULL,
    file_path   TEXT,
    line        INTEGER NOT NULL,
    snippet     TEXT NOT NULL,
    kept        INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_findings_rule_id ON findings(rule_id);
CREATE INDEX IF NOT EXISTS idx_findings_kept    ON findings(kept);
"""

_INSERT_FINDING = """
    INSERT OR IGNORE INTO findings
        (finding_id, rule_id, file_uri, file_path, line, snippet)
    VALUES
        (:finding_id, :rule_id, :file_uri, :file_path, :line, :snippet)
"""

_BATCH_SIZE = 1000


def connect(db_path: Path) -> sqlite3.Connection:
    """Открыть (или создать) файл БД."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Создать таблицы и индексы (если ещё нет)."""
    conn.executescript(_SCHEMA)
    conn.commit()


def insert_findings_batch(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Вставить findings батчами по 1000.

    INSERT OR IGNORE — дубликаты по finding_id молча пропускаются.
    Возвращает количество реально вставленных строк.
    """
    inserted = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i : i + _BATCH_SIZE]
        cur = conn.executemany(_INSERT_FINDING, batch)
        inserted += cur.rowcount
    conn.commit()
    return inserted
