"""RadiusEnricher — контекст = ±N строк вокруг места срабатывания.

Базовая (дефолтная) реализация Enricher. Это рабочий энричер для MVP, НЕ
заглушка: даёт LLM достаточно контекста для большинства findings BenchmarkJava.
Более умные реализации (метод целиком, дерево вызовов) добавляются в пакет
рядом и подключаются через enrich.get_enricher() — этот файл остаётся жить.

Свойства:
  - язык-агностичен: просто читает строки файла, одинаково для .java/.js/.xml;
  - дёшев по токенам: ±15 строк ≈ 300-450 токенов на qwen2.5-coder:7b —
    помещается в бюджет RTX 2060 6GB;
  - устойчив: путь не разрешён / файл недоступен → ok=False + snippet как fallback;
  - длинные строки (минифицированный JS и т.п.) обрезаются до _MAX_LINE_LEN —
    один файл-портянка не должен сожрать контекст модели.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from enrich.base import Context, Enricher, Finding

# Минифицированные файлы — одна строка на десятки КБ. Обрезаем, чтобы не
# раздувать промпт; для нормального исходника лимит недостижим.
_MAX_LINE_LEN = 500


class RadiusEnricher(Enricher):
    """Контекст — окно ±radius строк вокруг строки срабатывания."""

    def __init__(self, radius: int = 15) -> None:
        self.radius = radius

    def enrich(self, finding: Finding) -> Context:
        if not finding.file_path:
            return Context(
                finding.finding_id,
                finding.snippet,
                ok=False,
                note="file_path не разрешён в parse.py — fallback на snippet",
            )

        lines = _read_lines(Path(finding.file_path))
        if lines is None:
            return Context(
                finding.finding_id,
                finding.snippet,
                ok=False,
                note=f"файл недоступен ({finding.file_path}) — fallback на snippet",
            )

        # line из SARIF 1-based; окно зажимаем в границы файла
        idx = finding.line - 1
        lo = max(0, idx - self.radius)
        hi = min(len(lines), idx + self.radius + 1)

        out: list[str] = []
        for i in range(lo, hi):
            text = lines[i]
            if len(text) > _MAX_LINE_LEN:
                text = text[:_MAX_LINE_LEN] + " …(строка обрезана)"
            marker = ">>" if i == idx else "  "
            out.append(f"{marker} {i + 1:>5} | {text}")

        return Context(finding.finding_id, "\n".join(out), ok=True)


@lru_cache(maxsize=256)
def _read_lines(path: Path) -> tuple[str, ...] | None:
    """Файл построчно (без \\n). None — файла нет или не читается.

    LRU-кэш: команда enrich идёт по findings с ORDER BY file_path, поэтому
    findings одного файла встречаются подряд — файл читается с диска один раз.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return tuple(text.splitlines())
