"""Работа с SQLite-базой данных.

Таблицы:
  rules    — маппинг rule_id (UUID или строка) → человекочитаемое имя
  findings — все срабатывания из SARIF (rule_id уже хранится как name)
  groups   — группы findings по (rule_id, snippet) — Шаг 3
"""

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
    group_id    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Группы findings по (rule_id, snippet) — LLM зовётся один раз на группу (Шаг 3)
CREATE TABLE IF NOT EXISTS groups (
    group_id    TEXT PRIMARY KEY,
    rule_id     TEXT NOT NULL,
    snippet     TEXT NOT NULL,
    count       INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_findings_rule_id ON findings(rule_id);
CREATE INDEX IF NOT EXISTS idx_findings_kept    ON findings(kept);
CREATE INDEX IF NOT EXISTS idx_groups_rule_id   ON groups(rule_id);
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


def _migrate(conn: sqlite3.Connection) -> None:
    """Идемпотентные миграции для БД, созданных на предыдущих шагах.

    findings.group_id добавлен на Шаге 3 — для БД, распарсенной раньше,
    дотягиваем колонку через ALTER (перепарсивать 70 МБ SARIF не нужно).
    """
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(findings)")}
    if "group_id" not in cols:
        conn.execute("ALTER TABLE findings ADD COLUMN group_id TEXT")


def init_schema(conn: sqlite3.Connection) -> None:
    """Создать таблицы и индексы (если ещё нет)."""
    conn.executescript(_SCHEMA)
    _migrate(conn)
    # Индекс по group_id — после миграции: на старой БД до ALTER колонки ещё нет
    conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_group_id ON findings(group_id)")
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
