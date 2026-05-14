"""Группировка findings по точному snippet (Шаг 3).

LLM дорого звать на каждый из ~7.5k kept-findings. Внутри одного правила
snippet'ы повторяются десятками-сотнями раз — группируем по (rule_id, snippet),
LLM зовётся один раз на группу, вердикт распространяется на всю группу.

Нормализация snippet минимальная: trim + схлопывание пробелов. Литералы и
комментарии не трогаем — риск слить разные паттерны, выигрыш мал.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from typing import Any, Generator

_WS = re.compile(r"\s+")


def normalize_snippet(text: str) -> str:
    """trim + схлопывание любых пробельных последовательностей в один пробел."""
    return _WS.sub(" ", text).strip()


def compute_group_id(rule_id: str, normalized: str) -> str:
    """Стабильный ID группы = sha1(rule_id|normalized_snippet)[:10].

    По аналогии с finding_id в parse.py — детерминированный, одинаковый
    между прогонами.
    """
    raw = f"{rule_id}|{normalized}"
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


def apply(conn: sqlite3.Connection) -> dict[str, int | Generator[dict[str, Any], Any, None] | dict[str, Any] | Any]:
    """Пересчитать группы для всех findings с kept=1.

    Идемпотентно (как clean.apply): сбрасываем group_id и таблицу groups,
    затем строим заново — можно перезапускать после clean без перепарсинга.

    Возвращает {groups, findings, biggest}.
    """
    # Сброс — идемпотентность
    conn.execute("UPDATE findings SET group_id = NULL")
    conn.execute("DELETE FROM groups")

    # Один проход по kept-findings (~7.5k строк — спокойно помещается в память)
    groups: dict[str, dict] = {}
    updates: list[tuple[str, str]] = []

    for row in conn.execute(
        "SELECT finding_id, rule_id, snippet FROM findings WHERE kept=1"
    ):
        normalized = normalize_snippet(row["snippet"])
        gid = compute_group_id(row["rule_id"], normalized)

        group = groups.get(gid)
        if group is None:
            # Первый встреченный сырой snippet — репрезентативный сэмпл группы
            groups[gid] = {
                "rule_id": row["rule_id"],
                "snippet": row["snippet"],
                "count": 1,
            }
        else:
            group["count"] += 1

        updates.append((gid, row["finding_id"]))

    # Запись групп
    conn.executemany(
        "INSERT INTO groups (group_id, rule_id, snippet, count) VALUES (?, ?, ?, ?)",
        [(gid, g["rule_id"], g["snippet"], g["count"]) for gid, g in groups.items()],
    )

    # Привязка findings к группам
    conn.executemany(
        "UPDATE findings SET group_id = ? WHERE finding_id = ?", updates
    )

    conn.commit()

    biggest = max((g["count"] for g in groups.values()), default=0)
    return {
        "groups": len(groups),
        "findings": len(updates),
        "biggest": biggest,
    }
