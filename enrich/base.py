"""Контракт обогатителя контекста (Шаг 4) — точка подмены реализации.

Энричер получает Finding (строку из таблицы findings) и возвращает Context —
текстовый фрагмент исходника вокруг места срабатывания, который уйдёт в
LLM-промпт на Шаге 5.

Реализаций может быть несколько (±N строк, метод целиком, дерево вызовов).
Пайплайн (main.py: команда enrich → enrich.runner) работает ТОЛЬКО с этим
интерфейсом и берёт активную реализацию из enrich.get_enricher(). Заменить
энричер = переписать get_enricher(), пайплайн при этом не трогается.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """Вход энричера — поля из таблицы findings, нужные для обогащения."""

    finding_id: str
    rule_id: str
    file_path: str | None  # абсолютный путь, разрешённый в parse.py; None — не разрешён
    line: int
    snippet: str


@dataclass(frozen=True)
class Context:
    """Выход энричера — одна строка таблицы contexts."""

    finding_id: str
    text: str  # фрагмент исходника для LLM-промпта (или fallback при ok=False)
    ok: bool  # True — контекст извлечён; False — text это fallback (snippet)
    note: str = ""  # диагностика для логов: почему не удалось / что использовали


class Enricher(ABC):
    """Базовый класс энричера. Конкретные реализации лежат рядом в пакете."""

    @abstractmethod
    def enrich(self, finding: Finding) -> Context:
        """Извлечь контекст для одного finding'а."""
        raise NotImplementedError
