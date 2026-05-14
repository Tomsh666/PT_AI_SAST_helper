"""Пакет enrich — обогащение findings контекстом исходного кода (Шаг 4).

Содержит:
  base.py   — контракт Enricher + датаклассы Finding / Context
  radius.py — RadiusEnricher: контекст = ±N строк вокруг срабатывания (дефолт)
  runner.py — оркестрация: прогон энричера по всем kept-findings → таблица contexts

get_enricher() — единственная точка, через которую пайплайн получает энричер.
Сменить реализацию (метод целиком, дерево вызовов) = переписать тело
get_enricher(), не трогая runner.py и main.py.
"""

from enrich.base import Context, Enricher, Finding
from enrich.radius import RadiusEnricher


def get_enricher(radius: int = 15) -> Enricher:
    """Активная реализация энричера для команды `enrich`.

    Сейчас — RadiusEnricher (±radius строк). Когда появится энричер уровня
    метода / дерева вызовов — подменить здесь, остальной пайплайн не трогать.
    """
    return RadiusEnricher(radius=radius)


__all__ = ["Context", "Enricher", "Finding", "RadiusEnricher", "get_enricher"]
