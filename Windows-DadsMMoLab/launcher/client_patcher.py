"""
WoW 3.3.5a client patcher.

Patches the realmlist so the client connects to the local AzerothCore server
instead of the original (e.g. Blizzard or ChromieCraft) auth server.

Files targeted:
  Data/<locale>/realmlist.wtf   — primary, read on every launch
  WTF/Config.wtf                — optional override written after first login

Both files are backed up as <filename>.bak before any change.
"""
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import config
import log_handler as log

LOCAL_REALMLIST = "127.0.0.1"

_REALMLIST_CONTENT = (
    f"set realmlist {LOCAL_REALMLIST}\n"
    f"set patchlist {LOCAL_REALMLIST}\n"
)

# Locale sub-folders WoW 3.3.5a may use
_LOCALE_DIRS = [
    "enUS", "enGB", "deDE", "frFR", "esES", "esMX",
    "ruRU", "zhCN", "zhTW", "koKR", "ptBR", "ptPT",
]


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PatchTarget:
    path: Path
    exists: bool
    current_realmlist: str      # e.g. "logon.chromiecraft.com" or "127.0.0.1"
    is_patched: bool
    has_backup: bool
    label: str                  # short display name shown in UI


@dataclass
class PatchReport:
    wow_dir: Optional[Path]
    targets: list = field(default_factory=list)

    @property
    def all_patched(self) -> bool:
        return bool(self.targets) and all(t.is_patched for t in self.targets)

    @property
    def any_patched(self) -> bool:
        return any(t.is_patched for t in self.targets)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def scan() -> PatchReport:
    """Scan the WoW install for patchable files and return their current state."""
    wow_exe = config.load().get("wow_exe_path", "")
    if not wow_exe or not Path(wow_exe).exists():
        log.log("Client patcher: WoW.exe path not configured.", "WARN")
        return PatchReport(wow_dir=None)

    wow_dir = Path(wow_exe).parent
    targets = []

    # 1. Data/<locale>/realmlist.wtf
    for locale in _LOCALE_DIRS:
        candidate = wow_dir / "Data" / locale / "realmlist.wtf"
        if candidate.exists() or (wow_dir / "Data" / locale).is_dir():
            targets.append(_inspect(candidate, f"Data/{locale}/realmlist.wtf"))

    # Fallback: any realmlist.wtf found recursively under Data/
    if not targets:
        for found in (wow_dir / "Data").rglob("realmlist.wtf") if (wow_dir / "Data").is_dir() else []:
            rel = found.relative_to(wow_dir)
            targets.append(_inspect(found, str(rel)))

    # 2. WTF/Config.wtf (may not exist yet — still show it)
    config_wtf = wow_dir / "WTF" / "Config.wtf"
    targets.append(_inspect(config_wtf, "WTF/Config.wtf"))

    log.log(f"Client patcher: scanned {wow_dir} — {len(targets)} target(s) found.", "INFO")
    for t in targets:
        icon = "✅" if t.is_patched else ("○" if not t.exists else "❌")
        log.log(f"  {icon} {t.label}: {t.current_realmlist or '(not set)'}", "INFO")

    return PatchReport(wow_dir=wow_dir, targets=targets)


def patch(target: PatchTarget) -> tuple:
    """
    Patch a single target file.
    Returns (success: bool, message: str).
    """
    try:
        target.path.parent.mkdir(parents=True, exist_ok=True)

        # Backup existing file
        if target.path.exists() and not target.has_backup:
            bak = target.path.with_suffix(target.path.suffix + ".bak")
            shutil.copy2(target.path, bak)
            log.log(f"  Backed up → {bak.name}", "INFO")

        if target.path.suffix == ".wtf" and target.label.startswith("WTF/"):
            _patch_config_wtf(target.path)
        else:
            target.path.write_text(_REALMLIST_CONTENT, encoding="utf-8")

        log.log(f"  Patched: {target.label}", "INFO")
        return True, f"Patched → {LOCAL_REALMLIST}"
    except OSError as e:
        log.log(f"  Failed to patch {target.label}: {e}", "ERROR")
        return False, str(e)


def restore(target: PatchTarget) -> tuple:
    """Restore a file from its .bak backup."""
    bak = target.path.with_suffix(target.path.suffix + ".bak")
    if not bak.exists():
        return False, "No backup found."
    try:
        shutil.copy2(bak, target.path)
        log.log(f"  Restored: {target.label} from {bak.name}", "INFO")
        return True, f"Restored from {bak.name}"
    except OSError as e:
        return False, str(e)


def patch_all(report: PatchReport) -> tuple:
    """Patch every un-patched target. Returns (patched_count, errors)."""
    patched, errors = 0, []
    for t in report.targets:
        if not t.is_patched:
            ok, msg = patch(t)
            if ok:
                patched += 1
            else:
                errors.append(f"{t.label}: {msg}")
    return patched, errors


def restore_all(report: PatchReport) -> tuple:
    """Restore all targets that have backups."""
    restored, errors = 0, []
    for t in report.targets:
        if t.has_backup:
            ok, msg = restore(t)
            if ok:
                restored += 1
            else:
                errors.append(f"{t.label}: {msg}")
    return restored, errors


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────

def _inspect(path: Path, label: str) -> PatchTarget:
    exists = path.exists()
    has_backup = path.with_suffix(path.suffix + ".bak").exists()
    current = ""
    is_patched = False

    if exists:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            current = _extract_realmlist(text, label)
            is_patched = current == LOCAL_REALMLIST
        except OSError:
            pass
    elif label.startswith("WTF/"):
        # Config.wtf not created yet — treat as fine (no override)
        is_patched = True
        current = "(not created yet)"

    return PatchTarget(
        path=path,
        exists=exists,
        current_realmlist=current,
        is_patched=is_patched,
        has_backup=has_backup,
        label=label,
    )


def _extract_realmlist(text: str, label: str) -> str:
    """Pull the realmlist value out of a .wtf file."""
    if "Config.wtf" in label:
        m = re.search(r'SET\s+realmList\s+"([^"]+)"', text, re.IGNORECASE)
    else:
        m = re.search(r'set\s+realmlist\s+(\S+)', text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _patch_config_wtf(path: Path) -> None:
    """
    For Config.wtf: update the realmList line if present, add it if not.
    Preserve all other settings.
    """
    if not path.exists():
        return   # Not created yet — no override needed

    text = path.read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(r'(SET\s+realmList\s+)"[^"]+"', re.IGNORECASE)

    if pattern.search(text):
        patched = pattern.sub(f'\\1"{LOCAL_REALMLIST}"', text)
    else:
        patched = text.rstrip() + f'\nSET realmList "{LOCAL_REALMLIST}"\n'

    path.write_text(patched, encoding="utf-8")
