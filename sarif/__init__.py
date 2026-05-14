"""Пакет sarif — всё что связано с обработкой SARIF-отчётов.

Содержит:
  parse.py  — потоковое чтение и извлечение полей
  clean.py  — фильтрация мусорных правил (Шаг 2)
  group.py  — нормализация snippet и группировка (Шаг 3)
"""

from sarif.parse import iter_findings, parse_rules
from sarif.clean import apply as clean_findings, BLACKLIST
from sarif.group import apply as group_findings

__all__ = [
    "iter_findings",
    "parse_rules",
    "clean_findings",
    "BLACKLIST",
    "group_findings",
]
