"""Пакет sarif — всё что связано с обработкой SARIF-отчётов.

Содержит:
  parse.py  — потоковое чтение и извлечение полей
  clean.py  — фильтрация мусорных правил по blacklist
"""

from sarif.parse import iter_findings, parse_rules
from sarif.clean import apply as clean_findings, BLACKLIST

__all__ = [
    "iter_findings",
    "parse_rules",
    "clean_findings",
    "BLACKLIST",
]
