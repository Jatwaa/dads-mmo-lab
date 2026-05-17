"""
Reads and writes launcher settings to %APPDATA%\DadsMmoLab\settings.json.
Falls back to defaults on first run.
"""
import json
import os
from pathlib import Path

APPDATA = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
CONFIG_DIR = APPDATA / "DadsMmoLab"
CONFIG_FILE = CONFIG_DIR / "settings.json"

HOME = Path.home()

DEFAULTS = {
    "server_type": "base",
    "server_paths": {
        "base":        str(HOME / "wow-server"),
        "npcbots":     str(HOME / "wow-server-npcbots"),
        "playerbots":  str(HOME / "wow-server-playerbots"),
    },
    "wow_exe_path": "",
    "timeout_seconds": 900,
    "memory_limit_gb": 6,

    # ── NPCBots configuration ─────────────────────────────────────────────────
    # Wandering bots that roam zones, fight mobs, and engage players.
    # These map to docker-compose env vars via a .env file in the server folder.
    "npcbot_world_count":    40,     # Total wandering bots in the world
    "npcbot_faction_chance": 500,    # 0=all Alliance · 500=equal · 1000=all Horde

    # ── Playerbots (mod-playerbots) configuration ─────────────────────────────
    # Simulated player-bots that log in, quest, and trade on the AH.
    "playerbot_total_count":    50,  # Total random bots to maintain
    "playerbot_alliance_count": 25,  # Desired Alliance bots
    "playerbot_horde_count":    25,  # Desired Horde bots
    "playerbot_ah_buyer":       True,  # Bots bid on AH listings
    "playerbot_ah_seller":      True,  # Bots list items on the AH
}

# Common Steam install locations to auto-detect Wow.exe
_STEAM_WOW_CANDIDATES = [
    Path(r"C:\Program Files (x86)\World of Warcraft\Wow.exe"),
    Path(r"C:\Program Files\World of Warcraft\Wow.exe"),
    HOME / "Games" / "World of Warcraft" / "Wow.exe",
]


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base, preserving nested keys not present in override."""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return _deep_merge(DEFAULTS, saved)
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULTS.copy()


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def detect_wow_exe() -> str:
    """Return first Wow.exe path found in common locations, or empty string."""
    for candidate in _STEAM_WOW_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return ""


def log_file_path() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR / "launcher.log"


# ── Prereq check cache ────────────────────────────────────────────────────────

_CACHE_FILE = CONFIG_DIR / "prereq_cache.json"


def save_prereq_cache(results: list) -> None:
    """
    Persist the last prereq check results.
    results: list of {"key": str, "status": str, "detail": str}
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked_at": _now_iso(),
        "results": results,
    }
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except OSError:
        pass


def load_prereq_cache() -> tuple:
    """
    Returns (results_list, checked_at_str) or (None, None) if no valid cache.
    results_list: list of {"key", "status", "detail"}
    checked_at_str: human-readable timestamp string
    """
    if not _CACHE_FILE.exists():
        return None, None
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        results = payload.get("results", [])
        checked_at = payload.get("checked_at", "")
        label = _format_ts(checked_at)
        return results, label
    except (json.JSONDecodeError, OSError, KeyError):
        return None, None


def clear_prereq_cache() -> None:
    try:
        _CACHE_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat()


def _format_ts(iso: str) -> str:
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %d at %I:%M %p")
    except ValueError:
        return iso
