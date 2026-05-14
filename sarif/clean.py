"""Фильтрация мусорных правил.

Список правил — в sarif/blacklist.txt (одно правило на строку, # — комментарий).
Findings помечаются как kept=0 — данные остаются в БД, но исключаются
из группировки и LLM. Чтобы пересмотреть решение — отредактируй blacklist.txt
и запусти `python main.py clean` заново (без перепарсинга SARIF).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_BLACKLIST_FILE = Path(__file__).parent / "blacklist.txt"

# TODO(Шаг 5 — точность): пересмотреть blacklist.txt против полного списка
# из 48 правил боевого SARIF. Убедиться, что (а) в kept=1 не утекает мусор,
# (б) ничего реально уязвимого не отфильтровано. Сейчас список собран вручную
# по топу частот — см. таблицу правил в CLAUDE.md.
def load_blacklist(path: Path = _BLACKLIST_FILE) -> frozenset[str]:
    """Загрузить список правил из .txt файла."""
    rules: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rules.append(line)
    return frozenset(rules)


# Загружаем один раз при импорте модуля
BLACKLIST = load_blacklist()


def apply(conn: sqlite3.Connection, blacklist: frozenset[str] = BLACKLIST) -> dict[str, int]:
    """Пометить мусорные findings как kept=0.

    Сначала сбрасываем все в kept=1 (идемпотентность: можно перезапустить
    с обновлённым blacklist.txt без перепарсинга SARIF).

    Возвращает словарь {rule_id: кол-во помеченных}.
    """
    conn.execute("UPDATE findings SET kept=1")

    result: dict[str, int] = {}
    for rule_id in blacklist:
        cur = conn.execute(
            "UPDATE findings SET kept=0 WHERE rule_id=?", (rule_id,)
        )
        if cur.rowcount:
            result[rule_id] = cur.rowcount

    conn.commit()
    return result
