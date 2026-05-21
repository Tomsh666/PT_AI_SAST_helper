import sqlite3, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
conn = sqlite3.connect(Path("output/triage.db"))
conn.row_factory = sqlite3.Row

# ── запрос ────────────────────────────────────────────────────────────────────

SQL = """
    SELECT f.finding_id, f.file_uri, f.rule_id, fc.context
FROM findings f
JOIN finding_context fc USING (finding_id)
WHERE f.file_uri LIKE '%BenchmarkTest00001.java'
ORDER BY f.line
"""

# ─────────────────────────────────────────────────────────────────────────────

rows = conn.execute(SQL).fetchall()
print(f"{len(rows)} findings\n")
for r in rows:
    print(f"finding_id : {r['finding_id']}")
    print(f"file_uri   : {r['file_uri']}")
    print(f"rule   : {r['rule_id']}")
    print(f"context    :\n{r['context']}")
    print("-" * 80)
conn.close()
