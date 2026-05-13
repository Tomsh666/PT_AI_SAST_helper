"""Парсинг SARIF-отчётов от PT AI 5.4.

Потоковое чтение через ijson — файл не загружается целиком в память.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator

import ijson

# Путь внутри SARIF-дерева до массива срабатываний
_RESULTS_PREFIX = "runs.item.results.item"


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
) -> dict | None:
    """Извлекает нужные поля из одного SARIF-результата.

    Возвращает None если структура битая или нет rule_id.
    """
    rule_id: str = raw.get("ruleId", "").strip()
    if not rule_id:
        return None

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
) -> Iterator[dict]:
    """Потоковый генератор: читает SARIF и выдаёт findings по одному.

    Args:
        sarif_path:   путь к .sarif файлу
        project_root: корень исходников (inputs/projects/<name>)
        prefix_strip: явный архивный префикс для отрезания (необязательно)

    Yields:
        dict с полями: finding_id, rule_id, file_uri, file_path, line, snippet
    """
    with open(sarif_path, "rb") as f:
        for raw in ijson.items(f, _RESULTS_PREFIX):
            finding = _parse_result(raw, project_root, prefix_strip)
            if finding is not None:
                yield finding
