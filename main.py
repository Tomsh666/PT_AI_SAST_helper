from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path

# Windows: переключаем консоль на UTF-8 (иначе Rich ломается на cp1251)
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import typer
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn

import db
from sarif import iter_findings, parse_rules, clean_findings, context as ctx_mod


class ContextMod(str, Enum):
    radius = "radius"
    dataflow = "dataflow"  # stub


app = typer.Typer(
    help="LLM-триаж SARIF-отчётов от PT AI",
    no_args_is_help=True,
    add_completion=False,
)

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
    """Прочитать SARIF и залить findings в БД (kept=1).

    Требует, чтобы БД была создана командой `init` заранее.
    """
    if not db_path.exists():
        typer.secho(
            f"БД не найдена: {db_path}\nСначала выполни: python main.py init --db {db_path}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    conn = db.connect(db_path)

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
    db_path: Path = typer.Option(Path("output/triage.db"), "--db"),
    top: int = typer.Option(50, "--top", help="Сколько правил показать."),
) -> None:
    """Все правила с количеством findings (kept и отфильтрованные)."""
    from rich.table import Table
    from rich.console import Console

    conn = db.connect(db_path)
    console = Console()

    table = Table(title="Правила", show_lines=False)
    table.add_column("Кол-во", justify="right", style="cyan")
    table.add_column("%", justify="right")
    table.add_column("kept", justify="center")
    table.add_column("Правило")

    total = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    if total == 0:
        typer.secho("БД пустая — findings нет. Запусти parse.", fg=typer.colors.YELLOW)
        conn.close()
        return

    for row in conn.execute("""
        SELECT rule_id,
               COUNT(*) as cnt,
               SUM(kept) as kept_cnt
        FROM findings
        GROUP BY rule_id
        ORDER BY cnt DESC
        LIMIT ?
    """, (top,)):
        kept_all = row["kept_cnt"] == row["cnt"]
        pct = f"{row['cnt'] / total * 100:.1f}%"
        kept_label = "✓" if kept_all else "✗"
        style = "dim" if not kept_all else ""
        table.add_row(
            str(row["cnt"]), pct, kept_label, row["rule_id"],
            style=style,
        )

    console.print(table)
    conn.close()


@app.command()
def clean(
    db_path: Path = typer.Option(Path("output/triage.db"), "--db"),
) -> None:
    """Пометить мусорные findings как kept=0."""
    conn = db.connect(db_path)
    result = clean_findings(conn)

    total_marked = sum(result.values())
    typer.secho(f"Помечено kept=0: {total_marked:,} findings", fg=typer.colors.YELLOW, bold=True)
    for rule_id, cnt in sorted(result.items(), key=lambda x: -x[1]):
        typer.echo(f"  {cnt:>6}  {rule_id}")

    kept = conn.execute("SELECT COUNT(*) FROM findings WHERE kept=1").fetchone()[0]
    typer.secho(f"\nОсталось для обработки (kept=1): {kept:,}", fg=typer.colors.GREEN)
    conn.close()


@app.command()
def context(
    db_path: Path = typer.Option(Path("output/triage.db"), "--db"),
    context_mod: ContextMod = typer.Option(ContextMod.radius, "--context-mod"),
) -> None:
    """Рендерить код-контекст для всех findings и сохранить в finding_context."""
    if not db_path.exists():
        typer.secho(
            f"БД не найдена: {db_path}\nСначала выполни: python main.py init --db {db_path}",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=1)

    conn = db.connect(db_path)
    rows = conn.execute(
        "SELECT finding_id, file_path, line, rule_id FROM findings"
    ).fetchall()

    total = len(rows)
    if total == 0:
        typer.secho("Findings не найдены. Запусти parse.", fg=typer.colors.YELLOW)
        conn.close()
        return

    batch: list[dict] = []
    upserted = 0
    unavailable = 0

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Рендер контекста...", total=total)

        for row in rows:
            file_path = row["file_path"]

            if context_mod == ContextMod.radius:
                rendered = ctx_mod.render(file_path or "", row["line"], row["rule_id"])
                label = Path(file_path).name if file_path else "?"
                progress.update(task, description=f"[dim]{label}:{row['line']}[/dim]")
            else:
                rendered = f"(метод {context_mod.value} ещё не реализован)"

            if rendered == ctx_mod.UNAVAILABLE:
                unavailable += 1

            batch.append({"finding_id": row["finding_id"], "context": rendered})
            progress.advance(task)

            if len(batch) >= 1000:
                upserted += db.upsert_contexts_batch(conn, batch)
                batch.clear()

        if batch:
            upserted += db.upsert_contexts_batch(conn, batch)

    conn.close()
    typer.secho(f"\nГотово:", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  Всего findings     : {total:,}")
    typer.echo(f"  Записано контекстов: {upserted:,}")
    if unavailable:
        typer.secho(f"  Файл недоступен    : {unavailable:,}", fg=typer.colors.YELLOW)


if __name__ == "__main__":
    app()
