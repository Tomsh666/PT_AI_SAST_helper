# PT AI SAST Helper

Локальный LLM-триаж SARIF-отчётов от **PT AI 5.4**. На вход — SARIF-файл с десятками тысяч finding'ов, на выход — для каждого finding'а вердикт `REAL` / `FP` + уверенность 0–100, плюс развёрнутый разбор (deep-dive) по запросу. Всё работает офлайн: ни строки кода, ни SARIF за пределы машины не уходит.

## Пайплайн

```
SARIF файл
   ↓  parse        — потоково читаем findings из JSON
   ↓  clean        — выкидываем мусорные правила (несогласованная интеграция и т.п.)
   ↓  group        — нормализуем snippet, считаем group_id, дедуплицируем
   ↓  enrich       — берём ±15 строк из исходника
   ↓  triage       — один LLM-вызов на группу → JSON {verdict, confidence}
   ↓  report       — выгрузка md/csv, вердикт группы распространяется на все её findings
   ↓  dive         — по запросу, один finding → Markdown с разбором (CWE/OWASP/фикс)
```

Каждый этап — отдельная CLI-команда. Идём строго по этому порядку.

## Запуск окружения

```bash
# 1. Виртуальное окружение
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

# 2. Зависимости
pip install -r requirements.txt

# 3. Ollama (один раз)
ollama serve &
ollama pull qwen2.5-coder:7b-instruct-q4

# 4. CLI
python main.py --help
```

## Happy-path

```bash
python main.py init
python main.py parse  --sarif inputs/SARIF_reports/<file>.sarif \
                      --project-root inputs/projects/<name>
python main.py rules                  # смотрим топ-правила
python main.py clean                  # отсев мусора
python main.py group
python main.py enrich
python main.py triage --limit 20      # smoke-прогон 20 групп
python main.py status                 # счётчики, Ollama health
python main.py triage                 # полный прогон
python main.py report --format md --out output/reports/summary.md
python main.py dive <finding_id>      # точечный разбор
```

## Структура данных

- `inputs/SARIF_reports/*.sarif` — отчёты PT AI (в `.gitignore`, наружу не уходят).
- `inputs/projects/<name>/` — исходники соответствующего проекта.
- `output/triage.db` — SQLite со всем состоянием пайплайна (в `.gitignore`).
- `output/reports/*.md` — Markdown-выводы deep-dive и сводный отчёт.

### Path mapping

В SARIF путь имеет вид `./<archive-root>/path/to/file.ext`. Маппер отрезает `./<первый_сегмент>/` и склеивает остаток с `--project-root`. Имена «архивного корня» и папки проекта могут не совпадать (`BenchmarkJava-master` vs `BenchmarkJava`) — есть флаг `--prefix-strip` для override.

### Стабильный finding_id

`finding_id = sha1(f"{rule_id}|{file_uri}|{line}|{snippet}")[:8]` — между прогонами один и тот же finding получает один и тот же ID (по ТЗ).

### Группировка

`group_id = sha1(f"{rule_id}|{normalize_snippet(snippet)}")[:10]`. LLM зовётся один раз на группу, вердикт распространяется на все её findings виртуально через JOIN (`findings JOIN groups JOIN verdicts ON group_id`).

`normalize_snippet`: trim + collapse whitespace + удалить string/числовые литералы + удалить однострочные комментарии.

## Правила кода

- **Всё локально**, никаких внешних API. Единственный сетевой вызов — `http://localhost:11434` (Ollama).
- Пути — `pathlib.Path`, не строки.
- SARIF — **потоково** через `ijson` (файл может быть >70 МБ).
- I/O LLM — через **pydantic-модели**, JSON валидируется, при невалидном — retry с уточнением промпта.
- Маленькие, обсуждаемые шаги — каждое изменение в коде согласовывается перед записью.

## Сброс

```bash
# Снести БД и начать сначала
rm output/triage.db
python main.py init
```

## Ограничения MVP

- Один проект на одну БД (нет multi-tenancy).
- `concurrency=1` для LLM-вызовов (RTX 2060 6GB — параллелить нечем).
- Нет UI, только CLI.
- Deep-dive только по явному `dive <finding_id>` — не для всех findings разом.
- Список мусорных правил для `clean` собирается **руками** на Шаге 2, глядя на реальные правила в боевом SARIF.

## Открытые вопросы

- **Язык deep-dive**: по умолчанию `en` (CWE/OWASP — англоязычные источники, LLM точнее на английском). Есть флаг `--lang ru|en`, сравним на Шаге 7.
- **Список мусорных правил**: наполним вручную на Шаге 2 (`pt-sast rules` → блэклист).
- **Few-shot примеры в промпте**: не в MVP, добавим если zero-shot даёт плохую точность.
- **Параллелизм / Web UI / human-in-the-loop**: после MVP.

## План

Подробный пошаговый план реализации: `C:\Users\anton\.claude\plans\concurrent-brewing-castle.md`. Каждый шаг = один логический модуль = один коммит = обсуждение перед кодом.

Текущий статус шагов:
- [x] Шаг 0. Каркас + CLAUDE.md + .gitignore
- [ ] Шаг 1. `parse` + БД
- [ ] Шаг 2. `clean` + `rules`
- [ ] Шаг 3. `group`
- [ ] Шаг 4. `enrich` + `show`
- [ ] Шаг 5. `triage` (Ollama + промпт)
- [ ] Шаг 6. `report` + `status`
- [ ] Шаг 7. `dive`
