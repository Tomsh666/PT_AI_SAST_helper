# PT AI SAST Helper

Утилита для предобработки SARIF-отчётов от **PT AI 5.4** перед триажем.
Парсит SARIF в SQLite, фильтрует мусорные правила по blacklist, показывает
сводку по правилам.

БД — **одноразовая, под один скан**.

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Использование

```bash
# 1. Создать пустую БД
python main.py init --db output/triage.db

# 2. Залить findings из SARIF
python main.py parse \
    --sarif inputs/SARIF_reports/Report_BenchmarkJava.sarif \
    --project-root inputs/projects/BenchmarkJava \
    --db output/triage.db

# 3. Применить blacklist (kept=0 для мусора)
python main.py clean --db output/triage.db

# 4. Сводка по правилам
python main.py rules --db output/triage.db --top 50
```

## Структура

| Файл | Что делает |
|---|---|
| `main.py` | Typer CLI (`init`, `parse`, `clean`, `rules`) |
| `db.py` | SQLite-слой |
| `sarif/parse.py` | Потоковый ijson-парсер SARIF |
| `sarif/clean.py` | Фильтр по blacklist |
| `sarif/blacklist.txt` | Список правил, исключаемых из триажа |

## Схема БД

```sql
rules    (rule_id, name)
findings (finding_id, rule_id, file_uri, file_path, line, snippet, kept, created_at)
```

- `kept=1` — finding пойдёт в дальнейший триаж.
- `kept=0` — отфильтрован (мусор по blacklist).
- `finding_id` — `sha1(rule|file|line|snippet)[:16]`. Стабилен между прогонами.
