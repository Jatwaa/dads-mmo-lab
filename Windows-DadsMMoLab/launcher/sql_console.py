"""
SQL console backend — executes arbitrary queries against any AzerothCore database
via docker exec, same pattern as account_manager and character_editor.

Returns a QueryResult dataclass so the UI can decide how to render it.
"""
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Tuple

import log_handler as log

DB_CONTAINER = "ac_database"
MYSQL_USER   = "root"
MYSQL_PASS   = "azeroth"

DATABASES = ["acore_characters", "acore_auth", "acore_world"]

# Keywords whose queries produce rows in the result set
_SELECT_KEYWORDS = {"SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "CALL"}

# Keywords that are destructive — UI will warn before executing
_DANGEROUS_KEYWORDS = {"DROP", "TRUNCATE", "DELETE", "ALTER"}

MAX_DISPLAY_ROWS = 500


@dataclass
class QueryResult:
    ok:         bool
    is_select:  bool
    columns:    List[str]   = field(default_factory=list)
    rows:       List[list]  = field(default_factory=list)
    affected:   int         = 0
    elapsed_ms: float       = 0.0
    error:      str         = ""
    capped:     bool        = False   # True when rows were truncated to MAX_DISPLAY_ROWS


def execute(sql: str, db: str) -> QueryResult:
    """Run sql against db. Returns a QueryResult regardless of success/failure."""
    sql = sql.strip()
    if not sql:
        return QueryResult(ok=False, is_select=False, error="No query entered.")

    is_select = _is_select(sql)
    t0 = time.monotonic()

    # Run with --batch (no --silent so we keep column headers for SELECT)
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
            timeout=30,
        )
    except FileNotFoundError:
        return QueryResult(ok=False, is_select=is_select,
                           elapsed_ms=_ms(t0), error="docker not found on PATH.")
    except subprocess.TimeoutExpired:
        return QueryResult(ok=False, is_select=is_select,
                           elapsed_ms=_ms(t0), error="Query timed out after 30 s.")
    except Exception as exc:
        return QueryResult(ok=False, is_select=is_select,
                           elapsed_ms=_ms(t0), error=str(exc))

    elapsed = _ms(t0)

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        err = re.sub(r"mysql: \[Warning\].*\n?", "", err).strip()
        log.log(f"SQL console error ({db}): {err}", "ERROR")
        return QueryResult(ok=False, is_select=is_select, elapsed_ms=elapsed, error=err)

    stdout = r.stdout

    if is_select:
        lines = stdout.splitlines()
        if len(lines) < 1:
            return QueryResult(ok=True, is_select=True, elapsed_ms=elapsed)

        columns = lines[0].split("\t") if lines else []
        all_rows = [line.split("\t") for line in lines[1:] if line]
        capped   = len(all_rows) > MAX_DISPLAY_ROWS
        rows     = all_rows[:MAX_DISPLAY_ROWS]

        log.log(
            f"SQL console ({db}): {len(all_rows)} row(s) in {elapsed:.0f} ms"
            + (" [capped]" if capped else ""),
            "INFO",
        )
        return QueryResult(
            ok=True, is_select=True,
            columns=columns, rows=rows,
            elapsed_ms=elapsed, capped=capped,
        )
    else:
        # Non-SELECT: mysql --batch outputs "Query OK, N rows affected…" to stdout
        affected = _parse_affected(stdout)
        log.log(f"SQL console ({db}): {affected} row(s) affected in {elapsed:.0f} ms", "INFO")
        return QueryResult(
            ok=True, is_select=False,
            affected=affected, elapsed_ms=elapsed,
        )


def is_dangerous(sql: str) -> bool:
    """Return True if the first keyword looks destructive."""
    first = sql.strip().split()[0].upper() if sql.strip() else ""
    return first in _DANGEROUS_KEYWORDS


# ── helpers ───────────────────────────────────────────────────────────────────

def _is_select(sql: str) -> bool:
    first = sql.strip().split()[0].upper() if sql.strip() else ""
    return first in _SELECT_KEYWORDS


def _ms(t0: float) -> float:
    return (time.monotonic() - t0) * 1000


def _parse_affected(output: str) -> int:
    m = re.search(r"(\d+)\s+row", output, re.IGNORECASE)
    return int(m.group(1)) if m else 0
