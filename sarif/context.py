from __future__ import annotations

from pathlib import Path

BEFORE = 15
AFTER = 8

UNAVAILABLE = "(исходный файл недоступен)"

_file_cache: dict[str, list[str] | None] = {}


def _load(file_path: str) -> list[str] | None:
    if file_path not in _file_cache:
        try:
            _file_cache[file_path] = Path(file_path).read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            _file_cache[file_path] = None
    return _file_cache[file_path]


def render(file_path: str, line: int, rule_id: str) -> str:
    lines = _load(file_path)
    if lines is None:
        return UNAVAILABLE

    idx = line - 1  # 0-based
    start = max(0, idx - BEFORE)
    end = min(len(lines), idx + AFTER + 1)

    parts: list[str] = []
    for i in range(start, end):
        lineno = i + 1
        code = lines[i]
        if i == idx:
            parts.append(f"{lineno:>6}  {code}  ← PT AI: {rule_id}")
        else:
            parts.append(f"{lineno:>6}  {code}")

    return "\n".join(parts)
