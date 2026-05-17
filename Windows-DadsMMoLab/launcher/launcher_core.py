"""
Core launcher logic — state machine, Docker orchestration, WoW.exe watch.

State flow:
    IDLE → STARTING → WAITING_FOR_WORLD → READY
         → WAITING_FOR_WOW → WOW_RUNNING → SHUTTING_DOWN → IDLE

All public methods are non-blocking; they schedule work on a background thread.
Subscribe to state changes via set_on_state_change(callback).
"""
import subprocess
import threading
import time
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional

import psutil

import config
import log_handler as log

# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────

class State(Enum):
    IDLE            = auto()
    STARTING        = auto()
    WAITING_WORLD   = auto()
    READY           = auto()
    WAITING_WOW     = auto()
    WOW_RUNNING     = auto()
    SHUTTING_DOWN   = auto()
    ERROR           = auto()


# Human-readable labels shown in the status banner
STATE_LABELS = {
    State.IDLE:           "Idle — server not running",
    State.STARTING:       "Starting containers...",
    State.WAITING_WORLD:  "Waiting for world server...",
    State.READY:          "✅  AZEROTH IS READY!",
    State.WAITING_WOW:    "Waiting for WoW.exe to launch...",
    State.WOW_RUNNING:    "WoW is running ⚔️",
    State.SHUTTING_DOWN:  "Shutting down server...",
    State.ERROR:          "Error — check log",
}

# Banner accent colours (CustomTkinter colour strings)
STATE_COLORS = {
    State.IDLE:           "#3a3a3a",
    State.STARTING:       "#7a5500",
    State.WAITING_WORLD:  "#7a5500",
    State.READY:          "#1a5c2a",
    State.WAITING_WOW:    "#1a4060",
    State.WOW_RUNNING:    "#1a4060",
    State.SHUTTING_DOWN:  "#5c1a1a",
    State.ERROR:          "#8b0000",
}

# ─────────────────────────────────────────────────────────────────────────────
# AzerothCore container name fragments — same list as the bash script
# ─────────────────────────────────────────────────────────────────────────────
_AC_CONTAINER_PATTERNS = [
    "worldserver", "authserver", "ac-database",
    "ac-eluna", "ac-client", "ac-db-import",
]

# Sentinel in worldserver logs that means "server is ready"
_READY_SENTINEL = "ready..."


# ─────────────────────────────────────────────────────────────────────────────
# LauncherCore
# ─────────────────────────────────────────────────────────────────────────────

class LauncherCore:
    def __init__(self) -> None:
        self._state: State = State.IDLE
        self._on_state_change: Optional[Callable[[State], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._auto_launch_wow: bool = False
        self._cfg: dict = config.load()

    # ── public API ────────────────────────────────────────────────────────────

    def set_on_state_change(self, cb: Callable[[State], None]) -> None:
        self._on_state_change = cb

    @property
    def state(self) -> State:
        return self._state

    def reload_config(self) -> None:
        self._cfg = config.load()

    def start(self, auto_launch: bool = False) -> None:
        """Kick off the full launch sequence in a background thread."""
        if self._state not in (State.IDLE, State.ERROR):
            log.log("Start ignored — already running.", "WARN")
            return
        self._auto_launch_wow = auto_launch
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_sequence, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Force a docker compose down regardless of current state."""
        if self._state == State.IDLE:
            log.log("Stop ignored — server is not running.", "WARN")
            return
        self._stop_event.set()
        t = threading.Thread(target=self._do_shutdown, daemon=True)
        t.start()

    def launch_wow(self) -> None:
        """Open WoW.exe (non-blocking). Only meaningful when state is READY."""
        wow_path = self._cfg.get("wow_exe_path", "")
        if not wow_path or not Path(wow_path).exists():
            log.log("WoW.exe path not set or not found — configure in Settings.", "ERROR")
            return
        log.log(f"Launching WoW: {wow_path}")
        try:
            subprocess.Popen([wow_path], cwd=str(Path(wow_path).parent))
        except OSError as e:
            log.log(f"Failed to launch WoW: {e}", "ERROR")

    # ── internal helpers ──────────────────────────────────────────────────────

    def _set_state(self, new_state: State) -> None:
        self._state = new_state
        log.log(f"State → {new_state.name}")
        if self._on_state_change:
            self._on_state_change(new_state)

    def _server_dir(self) -> Path:
        server_type = self._cfg.get("server_type", "base")
        paths = self._cfg.get("server_paths", config.DEFAULTS["server_paths"])
        return Path(paths.get(server_type, paths["base"]))

    def _docker(self, *args: str, capture: bool = False) -> subprocess.CompletedProcess:
        cmd = ["docker", *args]
        log.log(f"$ {' '.join(cmd)}")
        return subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(self._server_dir()),
        )

    def _compose(self, *args: str, capture: bool = False) -> subprocess.CompletedProcess:
        cmd = ["docker", "compose", *args]
        log.log(f"$ {' '.join(cmd)}")
        return subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(self._server_dir()),
        )

    # ── checks ────────────────────────────────────────────────────────────────

    def _check_prerequisites(self) -> bool:
        server_dir = self._server_dir()
        if not server_dir.is_dir():
            log.log(f"Server folder not found: {server_dir}", "ERROR")
            log.log("Run the installer first, or check Settings → Server Path.", "ERROR")
            return False

        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            log.log("Docker is not running. Start Docker Desktop and try again.", "ERROR")
            return False

        log.log("Prerequisites OK.")
        return True

    # ── stop existing AC containers ───────────────────────────────────────────

    def _stop_existing_ac_containers(self) -> None:
        # Use `docker compose down` so containers are *removed* (not just stopped).
        # Stopped-but-not-removed containers keep their old volume mounts baked in;
        # `docker compose up` would just restart them rather than recreating them
        # with the current compose file, which causes stale config issues.
        log.log("Running docker compose down to clear any existing containers...")
        self._compose("down")
        log.log("All clear.")

    # ── startup ───────────────────────────────────────────────────────────────

    def _start_containers(self) -> bool:
        r = self._compose("up", "-d")
        if r.returncode == 0:
            log.log("Containers started!")
            return True

        log.log(f"docker compose up failed (exit {r.returncode}).", "ERROR")
        if r.stderr:
            for line in r.stderr.strip().splitlines():
                log.log(f"  {line}", "ERROR")
        return False

    # ── wait for world server ─────────────────────────────────────────────────

    def _wait_for_world(self) -> bool:
        timeout = int(self._cfg.get("timeout_seconds", 900))
        elapsed = 0
        log.log(f"Waiting up to {timeout // 60} min for world server...")
        log.log("First launch: 5–15 min  |  After first launch: ~30 sec")

        while elapsed < timeout:
            if self._stop_event.is_set():
                return False

            # Find worldserver container
            r = self._docker("ps", "--format", "{{.Names}}", capture=True)
            names = r.stdout.strip().splitlines() if r.returncode == 0 else []
            wc = next((n for n in names if "worldserver" in n.lower()), None)

            if wc:
                # No --tail limit: with playerbots, 500 bots log in after
                # "ready..." and push it hundreds of lines back.  The container
                # has only been running for minutes so full log is cheap.
                lr = self._docker("logs", wc, capture=True)
                combined = (lr.stdout or "") + (lr.stderr or "")
                if _READY_SENTINEL in combined:
                    log.log("World server is ready!")
                    return True

            dot_progress = elapsed // 5
            if dot_progress % 12 == 0 and elapsed > 0:
                log.log(f"  Still waiting... ({elapsed}s elapsed)")

            time.sleep(5)
            elapsed += 5

        log.log(f"Timed out after {timeout}s — world server may still be initialising.", "WARN")
        return False  # Soft timeout — we still surface READY so user can try

    # ── WoW.exe watch ─────────────────────────────────────────────────────────

    @staticmethod
    def _wow_running() -> bool:
        return any(
            p.info["name"] and p.info["name"].lower() in ("wow.exe", "wow-64.exe")
            for p in psutil.process_iter(["name"])
        )

    def _wait_for_wow_start(self) -> bool:
        log.log("Waiting for WoW.exe to launch (up to 5 min)...")
        for _ in range(60):
            if self._stop_event.is_set():
                return False
            if self._wow_running():
                return True
            time.sleep(5)
        log.log("WoW.exe not detected after 5 minutes.", "WARN")
        return False

    def _watch_wow_until_closed(self) -> None:
        log.log("WoW detected — have fun! ⚔️  Server shuts down when WoW closes.")
        while self._wow_running() and not self._stop_event.is_set():
            time.sleep(3)
        time.sleep(3)  # Brief grace period (same as bash script)
        log.log("WoW closed — initiating server shutdown.")

    # ── shutdown ──────────────────────────────────────────────────────────────

    def _do_shutdown(self) -> None:
        self._set_state(State.SHUTTING_DOWN)
        log.log("Running docker compose down...")
        r = self._compose("down")
        if r.returncode == 0:
            log.log("Server stopped cleanly. Safe to close. ✅")
        else:
            log.log(f"docker compose down exited {r.returncode}.", "WARN")
        self._set_state(State.IDLE)

    # ── full sequence ─────────────────────────────────────────────────────────

    def _run_sequence(self) -> None:
        try:
            # ── STARTING ─────────────────────────────────────────────────────
            self._set_state(State.STARTING)

            if not self._check_prerequisites():
                self._set_state(State.ERROR)
                return

            self._stop_existing_ac_containers()

            if not self._start_containers():
                self._set_state(State.ERROR)
                return

            if self._stop_event.is_set():
                self._do_shutdown()
                return

            # ── WAITING FOR WORLD ─────────────────────────────────────────────
            self._set_state(State.WAITING_WORLD)
            world_ready = self._wait_for_world()

            if self._stop_event.is_set():
                self._do_shutdown()
                return

            # ── READY ─────────────────────────────────────────────────────────
            # Surface READY even on soft timeout — user can still play
            self._set_state(State.READY)
            if not world_ready:
                log.log("⏳ Server may still be initialising — try launching WoW anyway.")

            # ── WAITING FOR WOW ───────────────────────────────────────────────
            self._set_state(State.WAITING_WOW)
            if self._auto_launch_wow:
                log.log("Auto-launching WoW...")
                self.launch_wow()
            wow_found = self._wait_for_wow_start()

            if self._stop_event.is_set():
                self._do_shutdown()
                return

            if wow_found:
                # ── WOW RUNNING ───────────────────────────────────────────────
                self._set_state(State.WOW_RUNNING)
                self._watch_wow_until_closed()
            else:
                log.log("Shutting down — WoW was never launched.")

            if self._stop_event.is_set():
                # Manual stop already triggered _do_shutdown on its own thread
                return

            # ── AUTO SHUTDOWN ─────────────────────────────────────────────────
            self._do_shutdown()

        except Exception as exc:
            log.log(f"Unexpected error in launch sequence: {exc}", "ERROR")
            self._set_state(State.ERROR)
            try:
                self._do_shutdown()
            except Exception:
                pass
