"""Парсинг SARIF-отчётов от PT AI 5.4.

Потоковое чтение через ijson — файл не загружается целиком в память.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator

import ijson

# Пути внутри SARIF-дерева
_RESULTS_PREFIX = "runs.item.results.item"
_RULES_PREFIX   = "runs.item.tool.driver.rules.item"


def parse_rules(sarif_path: Path) -> dict[str, str]:
    """Читает список правил из SARIF и возвращает маппинг rule_id → name.

    Правила хранятся в runs[0].tool.driver.rules[].
    Если name отсутствует — используем id как есть.
    """
    rules: dict[str, str] = {}
    with open(sarif_path, "rb") as f:
        for rule in ijson.items(f, _RULES_PREFIX):
            rule_id: str = rule.get("id", "").strip()
            name: str = rule.get("name", "").strip()
            if rule_id:
                rules[rule_id] = name if name else rule_id
    return rules


def _finding_id(rule_id: str, file_uri: str, line: int, snippet: str) -> str:
    """Стабильный ID = sha1(rule|file|line|snippet)[:8].

    Один и тот же finding между прогонами получает один и тот же ID.
    Точные дубликаты (rule+file+line+snippet совпадают) → одинаковый ID.
    """
    raw = f"{rule_id}|{file_uri}|{line}|{snippet}"
    return hashlib.sha1(raw.encode()).hexdigest()[:8]


def _resolve_path(
    file_uri: str,
    project_root: Path,
    prefix_strip: str | None,
) -> Path | None:
    """Преобразует SARIF-uri в реальный путь к файлу на диске.

    Пример (без prefix_strip):
        ./BenchmarkJava-master/src/main/java/.../Utils.java
        → отрезаем первый сегмент "BenchmarkJava-master"
        → src/main/java/.../Utils.java
        → project_root / src/main/java/.../Utils.java

    Если файл не найден — возвращает None (finding всё равно сохранится).
    """
    # Убираем ведущие "./" и "/"
    uri = file_uri.lstrip("./")

    if prefix_strip:
        # Явный override: отрезаем указанный префикс
        prefix = prefix_strip.strip("/")
        if uri.startswith(prefix + "/"):
            uri = uri[len(prefix) + 1 :]
    else:
        # Эвристика: отрезаем первый сегмент (имя архива)
        parts = uri.split("/", 1)
        uri = parts[1] if len(parts) == 2 else parts[0]

    resolved = project_root / uri
    return resolved if resolved.exists() else None


def _parse_result(
    raw: dict,
    project_root: Path,
    prefix_strip: str | None,
    rule_map: dict[str, str],
) -> dict | None:
    """Извлекает нужные поля из одного SARIF-результата.

    Возвращает None если структура битая или нет rule_id.
    UUID-шные rule_id заменяются на человекочитаемое имя из rule_map.
    """
    rule_id: str = raw.get("ruleId", "").strip()
    if not rule_id:
        return None

    # Заменяем UUID на имя правила (если есть в маппинге)
    rule_id = rule_map.get(rule_id, rule_id)

    locs = raw.get("locations", [])
    if not locs:
        return None

    pl = locs[0].get("physicalLocation", {})
    file_uri: str = pl.get("artifactLocation", {}).get("uri", "").strip()

    region = pl.get("region", {})
    line: int = region.get("startLine", 0)

    snippet_raw = region.get("snippet", {})
    snippet: str = snippet_raw.get("text", "").strip() if isinstance(snippet_raw, dict) else ""

    file_path = _resolve_path(file_uri, project_root, prefix_strip) if file_uri else None

    return {
        "finding_id": _finding_id(rule_id, file_uri, line, snippet),
        "rule_id": rule_id,
        "file_uri": file_uri,
        "file_path": str(file_path) if file_path else None,
        "line": line,
        "snippet": snippet,
    }


def iter_findings(
    sarif_path: Path,
    project_root: Path,
    prefix_strip: str | None = None,
    rule_map: dict[str, str] | None = None,
) -> Iterator[dict]:
    """Потоковый генератор: читает SARIF и выдаёт findings по одному.

    Args:
        sarif_path:   путь к .sarif файлу
        project_root: корень исходников (inputs/projects/<name>)
        prefix_strip: явный архивный префикс для отрезания (необязательно)
        rule_map:     маппинг rule_id → name из parse_rules() (необязательно)

    Yields:
        dict с полями: finding_id, rule_id, file_uri, file_path, line, snippet
    """
    _rule_map = rule_map or {}
    with open(sarif_path, "rb") as f:
        for raw in ijson.items(f, _RESULTS_PREFIX):
            finding = _parse_result(raw, project_root, prefix_strip, _rule_map)
            if finding is not None:
                yield finding
