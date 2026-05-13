"""PT AI SAST Helper — локальный LLM-триаж SARIF-отчётов от PT AI 5.4.

Точка входа CLI. Команды реализуются пошагово согласно плану в
C:\\Users\\anton\\.claude\\plans\\concurrent-brewing-castle.md
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows: переключаем консоль на UTF-8 (иначе Rich ломается на cp1251)
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import typer
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn

import db
from sarif import iter_findings, parse_rules

app = typer.Typer(
    help="LLM-триаж SARIF-отчётов от PT AI",
    no_args_is_help=True,
    add_completion=False,
)


def _todo(step: str, command: str) -> None:
    """Заглушка для нереализованных команд."""
    typer.secho(
        f"[{step}] '{command}' ещё не реализована.",
        fg=typer.colors.YELLOW,
    )
    raise typer.Exit(code=1)


@app.command()
def init(
    db_path: Path = typer.Option(
        Path("output/triage.db"),
        "--db",
        help="Путь к SQLite-файлу.",
    ),
) -> None:
    """Создать пустую БД и таблицы."""
    conn = db.connect(db_path)
    db.init_schema(conn)
    conn.close()
    typer.secho(f"БД создана: {db_path}", fg=typer.colors.GREEN)


@app.command()
def parse(
    sarif: Path = typer.Option(..., "--sarif", help="Путь к SARIF-файлу."),
    project_root: Path = typer.Option(
        ..., "--project-root", help="Корень исходников проекта."
    ),
    prefix_strip: str | None = typer.Option(
        None,
        "--prefix-strip",
        help="Префикс в SARIF-uri, который нужно отрезать (override эвристики).",
    ),
    db_path: Path = typer.Option(Path("output/triage.db"), "--db"),
) -> None:
    """Прочитать SARIF и залить findings в БД (kept=1)."""
    conn = db.connect(db_path)
    db.init_schema(conn)  # на случай если init не запускали

    # --- Шаг 1: правила ---
    typer.echo("Читаем правила из SARIF...")
    rule_map = parse_rules(sarif)
    db.insert_rules(conn, rule_map)
    typer.echo(f"  Правил найдено: {len(rule_map)}")

    # --- Шаг 2: findings ---
    total_read = 0
    total_inserted = 0
    batch: list[dict] = []

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Парсинг SARIF...", total=None)

        for finding in iter_findings(sarif, project_root, prefix_strip, rule_map):
            batch.append(finding)
            total_read += 1
            progress.update(task, advance=1, description=f"Прочитано: {total_read:,}")

            if len(batch) >= 1000:
                total_inserted += db.insert_findings_batch(conn, batch)
                batch.clear()

        # Последний неполный батч
        if batch:
            total_inserted += db.insert_findings_batch(conn, batch)

    conn.close()
    skipped = total_read - total_inserted
    typer.secho(f"\nГотово:", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  Прочитано из SARIF : {total_read:,}")
    typer.echo(f"  Записано в БД      : {total_inserted:,}")
    typer.echo(f"  Пропущено (дубли)  : {skipped:,}")


@app.command()
def rules(
    db: Path = typer.Option(Path("output/triage.db"), "--db"),
    top: int = typer.Option(20, "--top", help="Сколько правил показать."),
) -> None:
    """Топ-N правил по количеству срабатываний (помогает решить, что в мусор)."""
    _todo("Шаг 2", "rules")


@app.command()
def clean(
    db: Path = typer.Option(Path("output/triage.db"), "--db"),
) -> None:
    """Пометить мусорные findings как kept=0 (несогласованная интеграция и т.п.)."""
    _todo("Шаг 2", "clean")


@app.command()
def group(
    db: Path = typer.Option(Path("output/triage.db"), "--db"),
) -> None:
    """Нормализовать snippet'ы и сгруппировать по (rule_id, normalized_snippet)."""
    _todo("Шаг 3", "group")


@app.command()
def enrich(
    db: Path = typer.Option(Path("output/triage.db"), "--db"),
    radius: int = typer.Option(15, "--radius", help="Сколько строк ±вокруг."),
) -> None:
    """Подтянуть ±N строк контекста из исходников для репрезентативных findings."""
    _todo("Шаг 4", "enrich")


@app.command()
def triage(
    db: Path = typer.Option(Path("output/triage.db"), "--db"),
    model: str = typer.Option("qwen2.5-coder:7b-instruct-q4", "--model"),
    limit: int | None = typer.Option(None, "--limit"),
    rule: str | None = typer.Option(None, "--rule"),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
) -> None:
    """Пройти по группам и получить вердикты REAL/FP от LLM."""
    _todo("Шаг 5", "triage")


@app.command()
def dive(
    finding_id: str = typer.Argument(..., help="ID finding'а из БД."),
    db: Path = typer.Option(Path("output/triage.db"), "--db"),
    model: str = typer.Option("qwen2.5-coder:7b-instruct-q4", "--model"),
    lang: str = typer.Option("en", "--lang", help="Язык объяснения: en|ru."),
    out: Path = typer.Option(Path("output/reports"), "--out"),
) -> None:
    """Развёрнутый разбор одного finding'а (Markdown + CWE/OWASP + фикс)."""
    _todo("Шаг 7", "dive")


@app.command()
def report(
    db: Path = typer.Option(Path("output/triage.db"), "--db"),
    fmt: str = typer.Option("md", "--format", help="md|csv."),
    only: str | None = typer.Option(None, "--only", help="REAL|FP|UNSURE."),
    rule: str | None = typer.Option(None, "--rule"),
    out: Path = typer.Option(Path("output/reports/summary.md"), "--out"),
) -> None:
    """Сводный отчёт по findings с вердиктами."""
    _todo("Шаг 6", "report")


@app.command()
def status(
    db: Path = typer.Option(Path("output/triage.db"), "--db"),
) -> None:
    """Состояние БД и Ollama: счётчики, здоровье сервиса."""
    _todo("Шаг 6", "status")


@app.command()
def show(
    finding_id: str = typer.Argument(..., help="ID finding'а из БД."),
    db: Path = typer.Option(Path("output/triage.db"), "--db"),
) -> None:
    """Debug-вывод одного finding'а: метаданные + snippet + контекст."""
    _todo("Шаг 4", "show")


if __name__ == "__main__":
    app()
