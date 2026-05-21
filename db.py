from __future__ import annotations

import sqlite3
from pathlib import Path


_SCHEMA = """
-- Маппинг rule_id (UUID или строка) → человекочитаемое имя из SARIF
CREATE TABLE IF NOT EXISTS rules (
    rule_id  TEXT PRIMARY KEY,
    name     TEXT NOT NULL
);

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


CREATE INDEX IF NOT EXISTS idx_findings_rule_id  ON findings(rule_id);
CREATE INDEX IF NOT EXISTS idx_findings_kept     ON findings(kept);

CREATE TABLE IF NOT EXISTS finding_context (
    finding_id TEXT PRIMARY KEY,
    context    TEXT NOT NULL
);
"""

_INSERT_FINDING = """
    INSERT OR IGNORE INTO findings
        (finding_id, rule_id, file_uri, file_path, line, snippet)
    VALUES
        (:finding_id, :rule_id, :file_uri, :file_path, :line, :snippet)
"""

_INSERT_RULE = """
    INSERT OR IGNORE INTO rules (rule_id, name) VALUES (:rule_id, :name)
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


def insert_rules(conn: sqlite3.Connection, rules: dict[str, str]) -> None:
    """Вставить маппинг rule_id → name. INSERT OR IGNORE — повторы пропускаются."""
    rows = [{"rule_id": k, "name": v} for k, v in rules.items()]
    conn.executemany(_INSERT_RULE, rows)
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


def upsert_contexts_batch(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """INSERT OR REPLACE finding_context батчами. rows: [{finding_id, context}].
    Возвращает количество затронутых строк."""
    sql = "INSERT OR REPLACE INTO finding_context (finding_id, context) VALUES (:finding_id, :context)"
    affected = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i : i + _BATCH_SIZE]
        cur = conn.executemany(sql, batch)
        affected += cur.rowcount
    conn.commit()
    return affected


