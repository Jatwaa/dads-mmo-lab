"""
Account management — creates WoW accounts directly in the acore_auth database.

Modern AzerothCore uses SRP6 authentication (salt + verifier columns, both binary(32)).
  salt     = 32 random bytes
  verifier = g^x mod N  where:
               x  = SHA1(salt || SHA1(UPPER(user) || ":" || UPPER(pass)))
               g  = 7
               N  = 894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7
  All multi-byte integers use little-endian byte order (AzerothCore BigNumber convention).

We run SQL via `docker exec mysql` on ac_database — no extra port config needed.
"""
import hashlib
import os
import re
import subprocess
from typing import Tuple

import log_handler as log

DB_CONTAINER  = "ac_database"
MYSQL_USER    = "root"
MYSQL_PASS    = "azeroth"
AUTH_DB       = "acore_auth"

GM_LEVELS = {
    "Player (0)":        0,
    "Moderator (1)":     1,
    "GM (2)":            2,
    "Admin (3)":         3,
    "Console (4)":       4,
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def create_account(username: str, password: str, gm_level: int = 0) -> Tuple[bool, str]:
    """
    Create a WoW account and optionally grant GM access.
    Returns (success, message).
    """
    username = username.strip()
    password = password.strip()

    ok, err = _validate(username, password)
    if not ok:
        return False, err

    uname_up = username.upper()
    salt, verifier = _srp6_verifier(uname_up, password.upper())
    salt_hex     = salt.hex().upper()
    verifier_hex = verifier.hex().upper()

    # Check if account already exists
    exists_sql = f"SELECT COUNT(*) FROM account WHERE username='{uname_up}';"
    r = _mysql(exists_sql)
    if not r[0]:
        return False, f"DB query failed: {r[1]}"
    if "1" in r[1]:
        return False, f"Account '{uname_up}' already exists."

    # Create account (salt and verifier are binary(32), inserted via UNHEX)
    insert_sql = (
        f"INSERT INTO account (username, salt, verifier, email, joindate, expansion) "
        f"VALUES ('{uname_up}', UNHEX('{salt_hex}'), UNHEX('{verifier_hex}'), '', NOW(), 2);"
    )
    r = _mysql(insert_sql)
    if not r[0]:
        return False, f"Failed to create account: {r[1]}"

    log.log(f"Account created: {uname_up}", "INFO")

    # Set GM level if requested
    if gm_level > 0:
        gm_sql = (
            f"INSERT INTO account_access (id, gmlevel, RealmID) "
            f"SELECT id, {gm_level}, -1 FROM account WHERE username='{uname_up}';"
        )
        r = _mysql(gm_sql)
        if not r[0]:
            log.log(f"Account created but GM level failed: {r[1]}", "WARN")
            return True, f"Account '{uname_up}' created (GM level not set — {r[1]})"
        log.log(f"GM level {gm_level} granted to {uname_up}", "INFO")

    level_label = f", GM level {gm_level}" if gm_level > 0 else ""
    return True, f"Account '{uname_up}' created successfully{level_label}."


def list_accounts() -> Tuple[bool, list]:
    """Return (success, list_of_dicts) with all accounts and their GM levels."""
    sql = (
        "SELECT a.id, a.username, a.joindate, "
        "IFNULL(aa.gmlevel, 0) AS gmlevel "
        "FROM account a "
        "LEFT JOIN account_access aa ON a.id = aa.id AND aa.RealmID = -1 "
        "ORDER BY a.id;"
    )
    ok, output = _mysql(sql)
    if not ok:
        return False, []

    rows = []
    for line in output.strip().splitlines()[1:]:   # skip header
        parts = line.split("\t")
        if len(parts) >= 4:
            rows.append({
                "id":       parts[0].strip(),
                "username": parts[1].strip(),
                "joined":   parts[2].strip(),
                "gmlevel":  parts[3].strip(),
            })
    return True, rows


def delete_account(username: str) -> Tuple[bool, str]:
    uname_up = username.strip().upper()
    sql = f"DELETE FROM account WHERE username='{uname_up}';"
    ok, msg = _mysql(sql)
    if ok:
        log.log(f"Account deleted: {uname_up}", "INFO")
        return True, f"Account '{uname_up}' deleted."
    return False, msg


def set_gm_level(username: str, level: int) -> Tuple[bool, str]:
    uname_up = username.strip().upper()
    # Upsert GM level
    sql = (
        f"INSERT INTO account_access (id, gmlevel, RealmID) "
        f"SELECT id, {level}, -1 FROM account WHERE username='{uname_up}' "
        f"ON DUPLICATE KEY UPDATE gmlevel={level};"
    )
    ok, msg = _mysql(sql)
    if ok:
        log.log(f"GM level set to {level} for {uname_up}", "INFO")
        return True, f"GM level updated to {level} for '{uname_up}'."
    return False, msg


def db_reachable() -> bool:
    """Quick check — returns True if the auth database is accessible."""
    ok, _ = _mysql("SELECT 1;")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────

def _srp6_verifier(username_upper: str, password_upper: str) -> Tuple[bytes, bytes]:
    """
    Compute (salt, verifier) for AzerothCore SRP6 auth.

    Algorithm (matches AzerothCore SRP6.cpp):
      h1       = SHA1(username_upper || ":" || password_upper)
      x_bytes  = SHA1(salt || h1)
      x        = int(x_bytes, little-endian)
      verifier = g^x mod N  (32 bytes, little-endian)

    N and g are the standard WoW SRP6 constants.
    """
    _N = int("894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7", 16)
    _g = 7

    salt = os.urandom(32)

    h1 = hashlib.sha1((username_upper + ":" + password_upper).encode("utf-8")).digest()
    x_bytes = hashlib.sha1(salt + h1).digest()
    x = int.from_bytes(x_bytes, "little")

    v = pow(_g, x, _N)
    verifier = v.to_bytes(32, "little")

    return salt, verifier


def _mysql(sql: str) -> Tuple[bool, str]:
    """Run a SQL statement inside the database container. Returns (ok, output)."""
    try:
        r = subprocess.run(
            [
                "docker", "exec", DB_CONTAINER,
                "mysql",
                f"-u{MYSQL_USER}",
                f"-p{MYSQL_PASS}",
                "--batch",          # tab-separated, always outputs column headers
                AUTH_DB,
                "-e", sql,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if r.returncode == 0:
            return True, r.stdout
        err = (r.stderr or r.stdout).strip()
        # Strip the "mysql: [Warning]" password noise
        err = re.sub(r"mysql: \[Warning\].*\n?", "", err).strip()
        return False, err or f"mysql exited {r.returncode}"
    except FileNotFoundError:
        return False, "docker not found"
    except subprocess.TimeoutExpired:
        return False, "DB query timed out — is the database container running?"
    except Exception as exc:
        return False, str(exc)


def _validate(username: str, password: str) -> Tuple[bool, str]:
    if not username:
        return False, "Username cannot be empty."
    if not password:
        return False, "Password cannot be empty."
    if len(username) > 16:
        return False, "Username must be 16 characters or fewer."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if not re.match(r"^[A-Za-z0-9_]+$", username):
        return False, "Username may only contain letters, numbers, and underscores."
    return True, ""
