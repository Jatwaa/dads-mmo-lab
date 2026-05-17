"""
Entry point for Dad's MMO Lab Windows Launcher.

Start-up sequence:
  1. Bootstrap  — install Python deps if missing (works from any Python)
  2. App        — combined prereq checker + main launcher UI
"""
import subprocess
import sys
from pathlib import Path

# Ensure sibling modules importable whether run as a script or via PyInstaller
sys.path.insert(0, str(Path(__file__).parent))

# ── Bootstrap: install pip dependencies if any are missing ───────────────────
# This lets users double-click main.py (or launch.bat) without running setup.bat
# first. Safe to run multiple times — pip skips already-installed packages.
_REQUIREMENTS = Path(__file__).parent.parent / "requirements.txt"

def _bootstrap() -> None:
    try:
        import customtkinter  # noqa: F401 — fast path: already installed
        import docker          # noqa: F401
        import psutil          # noqa: F401
    except ImportError:
        print("Installing Python dependencies — this only happens once...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(_REQUIREMENTS)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Re-exec so the freshly installed packages are importable
        import os
        os.execv(sys.executable, [sys.executable] + sys.argv)

_bootstrap()

import customtkinter as ctk

import config
import log_handler as log
from app import App
from launcher_core import LauncherCore


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    log.log("Dad's MMO Lab — starting up", "INFO")
    log.log(f"Log file: {config.log_file_path()}", "INFO")

    core = LauncherCore()
    app  = App(core)
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()

    log.log("Launcher closed — goodbye.", "INFO")


if __name__ == "__main__":
    main()
