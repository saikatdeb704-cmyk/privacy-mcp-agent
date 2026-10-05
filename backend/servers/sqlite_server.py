"""
SQLite MCP Server
─────────────────
Exposes a local SQLite database to the agent over MCP (JSON-RPC via stdio).

Tools:
  list_tables              LOW     – names + row counts
  describe_database_schema LOW     – CREATE statements for all tables
  execute_read_query       MEDIUM  – SELECT / WITH only, read-only connection
  execute_mutation_query   HIGH    – INSERT / UPDATE / DELETE / DDL (needs approval)

Set AGENT_DB_PATH to point at your own database; otherwise a demo DB is created.
"""
import os
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("AGENT_DB_PATH", BASE_DIR / "data" / "enterprise_records.db")).resolve()
MAX_ROWS = 50

mcp = FastMCP("sqlite-mcp")


def _seed_demo_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE sales (
            id INTEGER PRIMARY KEY, region TEXT, product TEXT,
            revenue REAL, quarter TEXT, year INTEGER
        );
        CREATE TABLE employees (
            id INTEGER PRIMARY KEY, name TEXT, department TEXT,
            hire_date TEXT, salary REAL
        );
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY, company_name TEXT, contact_email TEXT, region TEXT
        );
        """
    )
    regions = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East"]
    products = ["Analytics Suite", "Edge Gateway", "Secure Vault"]
    base = {"North America": 950000, "Europe": 640000, "Asia Pacific": 480000,
            "Latin America": 210000, "Middle East": 150000}
    rows = []
    for year in (2023, 2024):
        for qi, q in enumerate(["Q1", "Q2", "Q3", "Q4"]):
            for ri, r in enumerate(regions):
                for pi, p in enumerate(products):
                    rev = base[r] * (1 + 0.04 * qi + 0.12 * (year - 2023)) * (0.8 + 0.15 * pi) / 3
                    rows.append((r, p, round(rev + ri * 1234.5, 2), q, year))
    cur.executemany("INSERT INTO sales (region, product, revenue, quarter, year) VALUES (?,?,?,?,?)", rows)
    cur.executemany(
        "INSERT INTO employees (name, department, hire_date, salary) VALUES (?,?,?,?)",
        [
            ("Aarav Sharma", "Engineering", "2021-03-14", 128000),
            ("Priya Patel", "Engineering", "2022-07-01", 115000),
            ("Liam Chen", "Sales", "2020-11-23", 98000),
            ("Sofia Rossi", "Marketing", "2023-01-09", 87000),
            ("Noah Williams", "Finance", "2019-05-30", 105000),
            ("Ananya Iyer", "Engineering", "2024-02-12", 109000),
            ("Mateo Garcia", "Sales", "2022-09-18", 92000),
        ],
    )
    cur.executemany(
        "INSERT INTO customers (company_name, contact_email, region) VALUES (?,?,?)",
        [
            ("Northwind Traders", "ops@northwind.local", "North America"),
            ("Contoso GmbH", "it@contoso.local", "Europe"),
            ("Tailspin Asia", "admin@tailspin.local", "Asia Pacific"),
            ("Fabrikam LatAm", "hello@fabrikam.local", "Latin America"),
        ],
    )
    conn.commit()
    conn.close()


if not DB_PATH.exists():
    _seed_demo_db()


def _format_rows(columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return f"Columns: {', '.join(columns)}\n(0 rows)"
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i, c in enumerate(columns)]
    line = "+".join("-" * (w + 2) for w in widths)
    out = [" | ".join(str(c).ljust(w) for c, w in zip(columns, widths)), line]
    out += [" | ".join(str(v).ljust(w) for v, w in zip(r, widths)) for r in rows]
    return "\n".join(out)


@mcp.tool()
def list_tables() -> str:
    """List all tables in the local database with their row counts."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        lines = [f"{n}: {conn.execute(f'SELECT COUNT(*) FROM \"{n}\"').fetchone()[0]} rows" for n in names]
        return f"Database: {DB_PATH.name}\n" + ("\n".join(lines) if lines else "No tables found.")
    finally:
        conn.close()


@mcp.tool()
def describe_database_schema() -> str:
    """Return the CREATE TABLE statements for every table. Call this before writing SQL."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL").fetchall()
        return "\n\n".join(r[0] for r in rows) or "No tables found."
    finally:
        conn.close()


@mcp.tool()
def execute_read_query(sql_query: str) -> str:
    """Run a read-only SQL query (SELECT or WITH) against the local SQLite database and return the rows."""
    q = sql_query.strip().rstrip(";")
    if not q.lower().startswith(("select", "with")):
        return "Security violation: only SELECT/WITH queries are allowed here. Use execute_mutation_query for changes."
    # Read-only connection: even a crafted query cannot modify data.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cur = conn.execute(q)
        columns = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        text = _format_rows(columns, rows[:MAX_ROWS])
        return text + (f"\n… truncated to {MAX_ROWS} rows" if truncated else f"\n({len(rows)} rows)")
    except sqlite3.Error as e:
        return f"SQL error: {e}"
    finally:
        conn.close()


@mcp.tool()
def execute_mutation_query(sql_query: str) -> str:
    """Run a data-modifying SQL statement (INSERT, UPDATE, DELETE, CREATE, ALTER, DROP). HIGH RISK – requires human approval."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(sql_query)
        conn.commit()
        return f"Statement executed. Rows affected: {cur.rowcount if cur.rowcount != -1 else 'n/a'}"
    except sqlite3.Error as e:
        conn.rollback()
        return f"SQL error: {e}"
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
