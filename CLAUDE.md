# PT AI SAST Helper

Локальный LLM-триаж SARIF-отчётов от **PT AI 5.4**. На вход — SARIF-файл с десятками тысяч finding'ов, на выход — для каждого finding'а вердикт `REAL` / `FP` + уверенность 0–100, плюс развёрнутый разбор (deep-dive) по запросу. Всё работает офлайн: ни строки кода, ни SARIF за пределы машины не уходит.

## Пайплайн

```
SARIF файл
   ↓  parse        — потоково читаем findings + правила из JSON
   ↓  clean        — помечаем мусорные правила как kept=0
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
python main.py rules                  # смотрим все правила с kept-статусом
python main.py clean                  # помечаем мусор (kept=0)
python main.py group
python main.py enrich
python main.py triage --limit 20      # smoke-прогон 20 групп
python main.py status                 # счётчики, Ollama health
python main.py triage                 # полный прогон
python main.py report --format md --out output/reports/summary.md
python main.py dive <finding_id>      # точечный разбор
```

## Структура проекта

```
PT_AI_SAST_helper/
├── sarif/
│   ├── __init__.py   — экспортирует iter_findings, parse_rules, clean_findings, group_findings
│   ├── parse.py      — потоковое чтение SARIF (ijson), маппинг путей, finding_id
│   ├── clean.py      — загружает blacklist.txt, функция apply()
│   ├── blacklist.txt — список правил для фильтрации (одно на строку, # — комментарий)
│   └── group.py      — нормализация snippet, group_id, группировка kept-findings
├── db.py             — SQLite: connect, init_schema, insert_rules, insert_findings_batch
├── main.py           — CLI (Typer): все команды
├── inputs/           — SARIF-файлы и исходники (в .gitignore)
├── output/           — triage.db, отчёты (в .gitignore)
├── requirements.txt
└── README.md
```

## Структура данных

- `inputs/SARIF_reports/*.sarif` — отчёты PT AI (в `.gitignore`).
- `inputs/projects/<name>/` — исходники проекта.
- `output/triage.db` — SQLite со всем состоянием пайплайна (в `.gitignore`).
- `output/reports/*.md` — Markdown-выводы deep-dive и сводный отчёт.

### Таблицы БД

| Таблица | Назначение |
|---|---|
| `rules` | Маппинг rule_id → человекочитаемое имя (из SARIF) |
| `findings` | Все срабатывания; `kept=0` — исключены из обработки |
| `groups` | Группы по (rule_id, snippet); `status` new/triaged — Шаг 3 |
| `contexts` | ±15 строк контекста из исходников — Шаг 4 |
| `verdicts` | LLM-вердикты по группам — Шаг 5 |
| `dives` | Развёрнутые разборы по finding'ам — Шаг 7 |

> Таблицы `contexts`, `verdicts`, `dives` — добавляются по мере реализации шагов.
> `findings.group_id` дотягивается в существующую БД через `db._migrate()` (ALTER, без перепарсинга SARIF).

### Path mapping

В SARIF путь вида `./<archive-root>/path/to/file.ext`. Маппер отрезает `./<первый_сегмент>/` и склеивает с `--project-root`. Флаг `--prefix-strip` для override (если имя архива ≠ имени папки проекта).

### Стабильный finding_id

`finding_id = sha1(f"{rule_id}|{file_uri}|{line}|{snippet}")[:8]` — один и тот же finding между прогонами получает один и тот же ID. Точные дубликаты (rule+file+line+snippet совпадают) → одинаковый ID → `INSERT OR IGNORE` вставляет только один.

### Группировка (Шаг 3)

`group_id = sha1(f"{rule_id}|{normalize_snippet(snippet)}")[:10]`. LLM зовётся один раз на группу. Вердикт группы распространяется на все findings виртуально через JOIN.

`normalize_snippet`: trim + схлопывание пробелов (`\s+` → один пробел). Литералы и комментарии **не трогаем** — в боевом SARIF snippet'ы и так почти точные дубли (88%), агрессивная нормализация дала бы риск слить разные паттерны при мизерном выигрыше. В SARIF от PT AI нет `codeFlows`/`relatedLocations` — кроме snippet'а группировать не по чему.

`group.apply()` идемпотентна: сбрасывает `group_id`/`groups` и строит заново — можно перезапускать после правки blacklist без перепарсинга. На тестовом SARIF: **7 558 kept-findings → 217 групп** (LLM-вызовов в ~35 раз меньше), крупнейшая группа — 780 findings.

## Правила фильтрации (sarif/clean.py — BLACKLIST)

После `parse` + `clean` на тестовом SARIF (BenchmarkJava, PT AI 5.4):
- **Всего finding'ов**: 99 046 (сырые) → 70 233 (уникальные) → **7 558 (kept=1, идут в LLM)**
- Список правил: `sarif/blacklist.txt` — редактировать вручную, потом `python main.py clean`

### Отфильтровано (kept=0)

| Правило | Кол-во | Причина |
|---|---|---|
| Несогласованная интеграция с внешними ресурсами | 60 724 | По ТЗ — архитектурное замечание |
| Раскрытие информации в статических файлах или константах | 818 | Информационная находка |
| Использование скомпрометированного ... криптографического алгоритма | 324 | Code quality, не уязвимость |
| Статический генератор случайных чисел | 218 | Code quality |
| Пустой блок обработки исключений | 148 | Code quality |
| Уязвимые функции хэширования | 141 | Code quality |
| Нарушение границ доверия | 88 | Архитектурное замечание |
| Использование браузерного api (в режиме SSR) | 36 | SSR-специфика, не уязвимость |
| TEST CWE-1321 - Potentially dangerous methods | 2 | Тестовое правило |
| Свойство shutdown/clientAuth/autoDeploy/deployOnStartup | 8 | Конфигурация Tomcat |
| Свойство error-code/http-only/secure/... (web.xml) | 6 | Конфигурация web.xml |
| Хранение минифицированного JS | 2 | Не уязвимость |
| Использование одиночной инструкции apt-get update | 1 | Docker best practice |
| Отсутствие директивы HEALTHCHECK | 1 | Docker best practice |
| Не удаленный код отладки | 3 | Code quality, не уязвимость |
| TEST CWE-1321 (Prototype Pollution) - Direct changes | 155 | JS-правило в Java-проекте |

### Остаётся для LLM (kept=1)

| Правило | Кол-во |
|---|---|
| Межсайтовое выполнение сценариев | 1 757 |
| Некорректные ограничения путей для каталогов (Path Traversal) | 1 209 |
| Инъекция в Cookie-параметре | 1 149 |
| Расщепление HTTP-ответа | 1 149 |
| Разглашение важной системной информации | 1 119 |
| Изменение произвольных файлов | 579 |
| Внедрение SQL-кода | 213 |
| Внедрение команд ОС | 110 |
| Чтение произвольного файла | 92 |
| Отсутствие в HTTPS-сессиях атрибута Secure | 36 |
| Отсутствует шифрование важных данных | 36 |
| Внедрение операторов LDAP | 24 |
| JQuery добавление HTML кода в DOM | 19 |
| Подделка записи файла журнала | 18 |
| Внедрение операторов XPath | 13 |
| Установка кода из недоверенных источников | 11 |
| Некорректная нейтрализация директив / Внедрение eval | 9 |
| JQuery небезопасная функция для DOM | 4 |
| Использование жестко закодированного пароля | 4 |
| JQuery заключение элемента в код HTML | 3 |
| DOM модификация HTML тега | 1 |
| ORM инъекция | 1 |
| Неконтролируемое использование ресурсов | 1 |
| Создание произвольного файла | 1 |


## Правила кода

- **Всё локально**, никаких внешних API. Единственный сетевой вызов — `http://localhost:11434` (Ollama).
- Пути — `pathlib.Path`, не строки.
- SARIF — **потоково** через `ijson` (файл может быть >70 МБ).
- I/O LLM — через **pydantic-модели**, JSON валидируется, при невалидном — retry.
- Маленькие, обсуждаемые шаги — каждое изменение в коде согласовывается перед записью.
- Windows: консоль переключается на UTF-8 в начале `main.py` (`sys.stdout.reconfigure`).

## Сброс

```bash
rm output/triage.db
python main.py init
python main.py parse --sarif ... --project-root ...
python main.py clean
```

## Ограничения MVP

- Один проект на одну БД (нет multi-tenancy).
- `concurrency=1` для LLM-вызовов (RTX 2060 6GB — параллелить нечем).
- Нет UI, только CLI.
- Deep-dive только по явному `dive <finding_id>`.

## Открытые вопросы

- **TODO в main.py (`#todo: разобраться с rule_map`)**: при LLM-триаже нужно решить, передавать ли rule_map в промпт или достаточно имени правила из findings. Разбираем на Шаге 5.
- **Язык deep-dive**: по умолчанию `en`. Флаг `--lang ru|en`, сравниваем на Шаге 7.
- **Few-shot примеры в промпте**: не в MVP.
- **Параллелизм / Web UI / human-in-the-loop**: после MVP.

## Статус шагов

- [x] Шаг 0. Каркас + CLAUDE.md + .gitignore
- [x] Шаг 1. `parse` + `init` + БД (таблицы `rules`, `findings`)
- [x] Шаг 2. `clean` + `rules`
- [x] Шаг 3. `group` (таблица `groups`, 217 групп из 7 558 kept-findings)
- [ ] Шаг 4. `enrich` + `show`
- [ ] Шаг 5. `triage` (Ollama + промпт)
- [ ] Шаг 6. `report` + `status`
- [ ] Шаг 7. `dive`
