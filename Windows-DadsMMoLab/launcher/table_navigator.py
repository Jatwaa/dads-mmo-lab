"""
Table navigator backend — lists tables across all AzerothCore databases,
describes their schema, and paginates row data.
All queries run via docker exec on ac_database.
"""
import re
import subprocess
from typing import Dict, List, Tuple

import log_handler as log

DB_CONTAINER = "ac_database"
MYSQL_USER   = "root"
MYSQL_PASS   = "azeroth"

DATABASES = ["acore_characters", "acore_auth", "acore_world"]

PAGE_SIZES = [25, 50, 100, 250]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def list_all_tables() -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    """
    Return (tables, errors) where:
      tables  = {db_name: [table, ...]}
      errors  = {db_name: error_string}  — only present when a DB failed
    """
    tables: Dict[str, List[str]] = {}
    errors: Dict[str, str]       = {}

    for db in DATABASES:
        ok, output = _mysql("SHOW TABLES;", db)
        if ok:
            rows = [l.strip() for l in output.splitlines()[1:] if l.strip()]
            tables[db] = rows
        else:
            tables[db] = []
            errors[db] = output
            log.log(f"Table navigator: {db} — {output}", "WARN")

    return tables, errors


def describe_table(table: str, db: str) -> Tuple[bool, List[dict]]:
    """
    Return (ok, columns) where each column is a dict with keys:
    field, type, null, key, default, extra.
    """
    ok, output = _mysql(f"DESCRIBE `{table}`;", db)
    if not ok:
        return False, []

    rows = []
    for line in output.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 6:
            rows.append({
                "field":   parts[0].strip(),
                "type":    parts[1].strip(),
                "null":    parts[2].strip(),
                "key":     parts[3].strip(),
                "default": parts[4].strip(),
                "extra":   parts[5].strip(),
            })
    return True, rows


def row_count(table: str, db: str, where: str = "") -> Tuple[bool, int]:
    """Return (ok, count). Uses WHERE clause when provided."""
    clause = f" WHERE {where}" if where.strip() else ""
    ok, output = _mysql(f"SELECT COUNT(*) FROM `{table}`{clause};", db)
    if not ok:
        return False, 0
    for line in output.splitlines()[1:]:
        try:
            return True, int(line.strip())
        except ValueError:
            pass
    return True, 0


def fetch_rows(
    table: str,
    db: str,
    limit: int = 50,
    offset: int = 0,
    where: str = "",
) -> Tuple[bool, List[str], List[List[str]]]:
    """
    Return (ok, columns, rows).
    rows is a list of lists — each inner list matches columns by index.
    """
    clause = f" WHERE {where}" if where.strip() else ""
    sql = f"SELECT * FROM `{table}`{clause} LIMIT {limit} OFFSET {offset};"
    ok, output = _mysql(sql, db)
    if not ok:
        return False, [], []

    lines = output.splitlines()
    if not lines:
        return True, [], []

    columns = lines[0].split("\t")
    rows    = []
    for line in lines[1:]:
        if line:
            parts = line.split("\t")
            # Pad short rows (e.g. trailing NULLs stripped by mysql)
            parts += [""] * (len(columns) - len(parts))
            rows.append(parts)

    return True, columns, rows


# ─────────────────────────────────────────────────────────────────────────────
# Internal
# ─────────────────────────────────────────────────────────────────────────────

def _mysql(sql: str, db: str) -> Tuple[bool, str]:
    try:
        r = subprocess.run(
            [
                "docker", "exec", DB_CONTAINER,
                "mysql",
                f"-u{MYSQL_USER}",
                f"-p{MYSQL_PASS}",
                "--batch",
                db,
                "-e", sql,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        if r.returncode == 0:
            return True, r.stdout
        err = (r.stderr or r.stdout).strip()
        err = re.sub(r"mysql: \[Warning\].*\n?", "", err).strip()
        return False, err or f"mysql exited {r.returncode}"
    except FileNotFoundError:
        return False, "docker not found"
    except subprocess.TimeoutExpired:
        return False, "Query timed out"
    except Exception as exc:
        return False, str(exc)
