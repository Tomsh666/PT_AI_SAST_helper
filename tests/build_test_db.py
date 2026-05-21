import argparse
import csv
import re
import sqlite3
from pathlib import Path

from rich.console import Console

BENCHMARK_RE = re.compile(r"BenchmarkTest(\d{5})")

DDL = """
DROP TABLE IF EXISTS findings;
DROP INDEX IF EXISTS idx_test_file_name;
DROP INDEX IF EXISTS idx_test_category;
CREATE TABLE findings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id TEXT NOT NULL,
    file_name  TEXT NOT NULL,
    file_path  TEXT NOT NULL,
    line       INTEGER NOT NULL,
    snippet    TEXT,
    rule_id    TEXT NOT NULL,
    category   TEXT NOT NULL,
    real       INTEGER NOT NULL,
    kept       INTEGER NOT NULL
);
CREATE INDEX idx_test_file_name ON findings(file_name);
CREATE INDEX idx_test_category  ON findings(category);
"""


def load_csv(csv_path: Path) -> dict[str, tuple[str, int]]:
    result: dict[str, tuple[str, int]] = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0].startswith("#"):
                continue
            test_name = row[0].strip()
            category  = row[1].strip()
            real_int  = 1 if row[2].strip().lower() == "true" else 0
            result[test_name] = (category, real_int)
    return result


def main() -> None:
    base = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description="Build tests/data/test.db")
    parser.add_argument("--triage-db",   default=str(base / "output" / "triage.db"))
    parser.add_argument("--csv",         default=str(base / "inputs" / "projects" / "BenchmarkJava" / "expectedresults-1.2.csv"))
    parser.add_argument("--test-db",     default=str(base / "tests" / "data" / "test.db"))
    args = parser.parse_args()

    ground_truth = load_csv(Path(args.csv))

    test_db = Path(args.test_db)
    test_db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(test_db)
    con.executescript(DDL)
    con.close()

    src = sqlite3.connect(Path(args.triage_db))
    src.text_factory = bytes
    rows = src.execute(
        "SELECT rule_id, file_path, kept FROM findings WHERE (file_path IS NOT NULL) AND (file_path LIKE '%.java') ORDER BY file_path"
    ).fetchall()
    src.close()

    dst = sqlite3.connect(test_db)
    insert = "INSERT INTO findings (file_name, file_path, rule_id, category, real, kept) VALUES (?,?,?,?,?,?)"

    matched, skipped = 0, 0
    matched_tests: set[str] = set()
    for rule_id_b, file_path_b, kept in rows:
        file_path = file_path_b.decode("utf-8")
        m = BENCHMARK_RE.search(file_path)
        if not m:
            skipped += 1
            continue
        test_name = f"BenchmarkTest{m.group(1)}"
        if test_name not in ground_truth:
            skipped += 1
            continue
        rule_id = rule_id_b.decode("utf-8")
        category, real_int = ground_truth[test_name]
        file_name = Path(file_path.replace("\\", "/")).name
        dst.execute(insert, (file_name, file_path, rule_id, category, real_int, kept))
        matched_tests.add(test_name)
        matched += 1

    dst.commit()
    dst.close()

    count = sqlite3.connect(test_db).execute("SELECT COUNT(*) FROM findings").fetchone()[0]

    console = Console()
    console.print(f"[green]Вставлено:[/green]      {count}")
    console.print(f"[yellow]Пропущено:[/yellow]     {skipped} (helpers/JS/configs)")
    console.print(f"[cyan]Покрыто тестов:[/cyan] {len(matched_tests)} / {len(ground_truth)}")


if __name__ == "__main__":
    main()
