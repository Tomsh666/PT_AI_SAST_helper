"""Оркестрация Шага 4 — прогон активного энричера по всем kept-findings.

Не зависит от конкретного энричера: берёт его из enrich.get_enricher().
Идемпотентно (как clean.apply / group.apply): DELETE FROM contexts +
построение заново — можно перезапускать после правки blacklist / group
без перепарсинга SARIF.
"""

from __future__ import annotations

import sqlite3
from typing import Callable

import db
from enrich import get_enricher
from enrich.base import Finding

_SELECT_KEPT = """
    SELECT finding_id, rule_id, file_path, line, snippet
    FROM findings
    WHERE kept = 1
    ORDER BY file_path, line
"""

_BATCH_SIZE = 1000


def apply(
    conn: sqlite3.Connection,
    *,
    radius: int = 15,
    on_advance: Callable[[], None] | None = None,
) -> dict[str, int]:
    """Обогатить контекстом все findings с kept=1.

    on_advance — необязательный колбэк, вызывается раз на каждый обработанный
    finding (для прогресс-бара в main.py).

    Возвращает {findings, ok, failed}.
    """
    enricher = get_enricher(radius=radius)

    # Идемпотентность: строим contexts заново. ORDER BY file_path в _SELECT_KEPT
    # держит findings одного файла подряд — LRU-кэш чтения в энричере попадает.
    conn.execute("DELETE FROM contexts")
    rows = conn.execute(_SELECT_KEPT).fetchall()

    batch: list[tuple] = []
    ok = 0
    failed = 0

    for row in rows:
        finding = Finding(
            finding_id=row["finding_id"],
            rule_id=row["rule_id"],
            file_path=row["file_path"],
            line=row["line"],
            snippet=row["snippet"],
        )
        ctx = enricher.enrich(finding)
        batch.append((ctx.finding_id, ctx.text, int(ctx.ok), ctx.note))
        if ctx.ok:
            ok += 1
        else:
            failed += 1

        if len(batch) >= _BATCH_SIZE:
            db.insert_contexts_batch(conn, batch)

            batch.clear()

        if on_advance is not None:
            on_advance()

    if batch:
        db.insert_contexts_batch(conn, batch)

    conn.commit()
    return {"findings": len(rows), "ok": ok, "failed": failed}
