"""
Pre-launch prerequisite checking and auto-installation logic.

Each prereq has a check_fn and optionally an install_fn.
All functions are designed to run from a background thread.
install_fn receives a log_fn(msg) callback to stream progress to the UI log.
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional, Tuple

import config

LogFn = Callable[[str, str], None]  # (message, level)


# ─────────────────────────────────────────────────────────────────────────────
# Status model
# ─────────────────────────────────────────────────────────────────────────────

class CheckStatus(Enum):
    PENDING          = auto()
    CHECKING         = auto()
    OK               = auto()
    WARNING          = auto()   # installed but needs attention
    MISSING          = auto()   # not installed / not found
    INSTALLING       = auto()
    FAILED           = auto()
    REBOOT_REQUIRED  = auto()


STATUS_ICON: dict = {
    CheckStatus.PENDING:         "○",
    CheckStatus.CHECKING:        "⏳",
    CheckStatus.OK:              "✅",
    CheckStatus.WARNING:         "⚠️",
    CheckStatus.MISSING:         "❌",
    CheckStatus.INSTALLING:      "⏳",
    CheckStatus.FAILED:          "❌",
    CheckStatus.REBOOT_REQUIRED: "🔄",
}

STATUS_COLOR: dict = {
    CheckStatus.PENDING:         "#606060",
    CheckStatus.CHECKING:        "#c08000",
    CheckStatus.OK:              "#1a8c3a",
    CheckStatus.WARNING:         "#c07000",
    CheckStatus.MISSING:         "#8c1a1a",
    CheckStatus.INSTALLING:      "#c08000",
    CheckStatus.FAILED:          "#8c0000",
    CheckStatus.REBOOT_REQUIRED: "#1a5090",
}


@dataclass
class PrereqItem:
    key: str
    name: str
    description: str
    required: bool = True
    can_auto_install: bool = True
    # runtime — mutated by checker
    status: CheckStatus = CheckStatus.PENDING
    detail: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Check functions  →  (CheckStatus, detail_string)
# ─────────────────────────────────────────────────────────────────────────────

def check_python() -> Tuple[CheckStatus, str]:
    v = sys.version_info
    label = f"Python {v.major}.{v.minor}.{v.micro}"
    if v >= (3, 11):
        return CheckStatus.OK, label
    if v >= (3, 8):
        return CheckStatus.WARNING, f"{label}  (3.11+ recommended)"
    return CheckStatus.MISSING, f"{label}  — upgrade to Python 3.11+"


def check_winget() -> Tuple[CheckStatus, str]:
    if not shutil.which("winget"):
        return CheckStatus.MISSING, "winget not available on this machine"
    r = _run(["winget", "--version"])
    if r.returncode == 0:
        return CheckStatus.OK, r.stdout.strip().splitlines()[0] if r.stdout.strip() else "winget found"
    return CheckStatus.WARNING, "winget found but returned an error"


def check_wsl2() -> Tuple[CheckStatus, str]:
    if not shutil.which("wsl"):
        return CheckStatus.MISSING, "WSL not installed"
    r = _run(["wsl", "--list", "--verbose"], timeout=10)
    output = (r.stdout or "") + (r.stderr or "")
    if "2" in output:
        return CheckStatus.OK, "WSL2 is available"
    r2 = _run(["wsl", "--status"], timeout=10)
    if r2.returncode == 0:
        return CheckStatus.WARNING, "WSL present — verify WSL2 is the default version"
    return CheckStatus.MISSING, "WSL2 not configured"


def check_docker() -> Tuple[CheckStatus, str]:
    if not shutil.which("docker"):
        return CheckStatus.MISSING, "Docker Desktop not installed"
    try:
        r = _run(["docker", "info"], timeout=8)
    except subprocess.TimeoutExpired:
        return CheckStatus.WARNING, "Docker installed but daemon timed out — open Docker Desktop"
    if r.returncode != 0:
        return CheckStatus.WARNING, "Docker installed but daemon not running — open Docker Desktop"
    for line in (r.stdout or "").splitlines():
        if "Server Version" in line:
            return CheckStatus.OK, line.strip()
    return CheckStatus.OK, "Docker daemon is running"


def check_git() -> Tuple[CheckStatus, str]:
    if not shutil.which("git"):
        return CheckStatus.MISSING, "Git not installed"
    r = _run(["git", "--version"])
    if r.returncode == 0:
        return CheckStatus.OK, r.stdout.strip()
    return CheckStatus.WARNING, "git found but --version failed"


def check_server_dir() -> Tuple[CheckStatus, str]:
    cfg = config.load()
    server_type = cfg.get("server_type", "base")
    paths = cfg.get("server_paths", config.DEFAULTS["server_paths"])
    path = Path(paths.get(server_type, ""))
    if path.is_dir() and (path / "docker-compose.yml").exists():
        return CheckStatus.OK, str(path)
    if path.is_dir():
        return CheckStatus.WARNING, f"{path} exists but docker-compose.yml is missing — run Setup"
    return CheckStatus.MISSING, f"Not found: {path} — run Setup below"


def check_wow_exe() -> Tuple[CheckStatus, str]:
    cfg = config.load()
    wow_path = cfg.get("wow_exe_path", "")
    if wow_path and Path(wow_path).exists():
        return CheckStatus.OK, wow_path
    detected = config.detect_wow_exe()
    if detected:
        return CheckStatus.WARNING, f"Found at {detected} — set path in launcher Settings"
    return CheckStatus.MISSING, "WoW 3.3.5a client not found — browse to set path"


# ─────────────────────────────────────────────────────────────────────────────
# Install functions  →  (success: bool, message: str)
# ─────────────────────────────────────────────────────────────────────────────

def install_wsl2(log_fn: LogFn) -> Tuple[bool, str]:
    log_fn("Running: wsl --install ...", "INFO")
    log_fn("This may open a UAC prompt for administrator access.", "INFO")
    try:
        r = _run(["wsl", "--install"], timeout=180)
        if r.stdout:
            for line in r.stdout.strip().splitlines():
                log_fn(f"  {line}", "INFO")
        if r.returncode in (0, 1):
            return True, "WSL2 installed — a system REBOOT is required to complete setup."
        return False, f"wsl --install exited {r.returncode}: {(r.stderr or '')[:200]}"
    except subprocess.TimeoutExpired:
        return False, "wsl --install timed out — run manually in an admin PowerShell."
    except FileNotFoundError:
        return False, "wsl command not found."


def install_docker(log_fn: LogFn) -> Tuple[bool, str]:
    log_fn("Installing Docker Desktop via winget — this may take 5–10 minutes...", "INFO")
    try:
        r = _run([
            "winget", "install", "--id", "Docker.DockerDesktop", "-e",
            "--accept-source-agreements", "--accept-package-agreements",
        ], timeout=600)
        if r.stdout:
            for line in r.stdout.strip().splitlines()[-10:]:  # last 10 lines
                log_fn(f"  {line}", "INFO")
        if r.returncode == 0:
            return True, "Docker Desktop installed — launch Docker Desktop from the Start menu, then re-check."
        return False, f"winget install Docker failed (exit {r.returncode}): {(r.stderr or '')[:300]}"
    except subprocess.TimeoutExpired:
        return False, "Docker install timed out — try installing Docker Desktop manually."
    except FileNotFoundError:
        return False, "winget not found — install Docker Desktop from https://www.docker.com/products/docker-desktop/"


def install_git(log_fn: LogFn) -> Tuple[bool, str]:
    log_fn("Installing Git via winget...", "INFO")
    try:
        r = _run([
            "winget", "install", "--id", "Git.Git", "-e",
            "--accept-source-agreements", "--accept-package-agreements",
        ], timeout=300)
        if r.stdout:
            for line in r.stdout.strip().splitlines()[-5:]:
                log_fn(f"  {line}", "INFO")
        if r.returncode == 0:
            return True, "Git installed — restart the launcher for PATH changes to take effect."
        return False, f"winget install Git failed (exit {r.returncode}): {(r.stderr or '')[:300]}"
    except subprocess.TimeoutExpired:
        return False, "Git install timed out."
    except FileNotFoundError:
        return False, "winget not found — install Git from https://git-scm.com/download/win"


# ─────────────────────────────────────────────────────────────────────────────
# Prereq registry
# ─────────────────────────────────────────────────────────────────────────────

def build_prereq_list() -> list:
    return [
        PrereqItem("python", "Python 3.11+",
                   "Runtime for this launcher",
                   required=True, can_auto_install=False),
        PrereqItem("winget", "Windows Package Manager",
                   "Auto-installs other tools (winget)",
                   required=False, can_auto_install=False),
        PrereqItem("wsl2",   "WSL2",
                   "Windows Subsystem for Linux — required by Docker",
                   required=True, can_auto_install=True),
        PrereqItem("docker", "Docker Desktop",
                   "Runs the AzerothCore WoW server containers",
                   required=True, can_auto_install=True),
        PrereqItem("git",    "Git",
                   "Used for server module updates",
                   required=False, can_auto_install=True),
        PrereqItem("server", "WoW Server Folder",
                   "Server install directory with docker-compose.yml",
                   required=True, can_auto_install=False),
        PrereqItem("wow",    "WoW.exe (3.3.5a client)",
                   "World of Warcraft Wrath of the Lich King client",
                   required=True, can_auto_install=False),
    ]


CHECK_FN: dict = {
    "python": check_python,
    "winget": check_winget,
    "wsl2":   check_wsl2,
    "docker": check_docker,
    "git":    check_git,
    "server": check_server_dir,
    "wow":    check_wow_exe,
}

INSTALL_FN: dict = {
    "wsl2":   install_wsl2,
    "docker": install_docker,
    "git":    install_git,
}


# ─────────────────────────────────────────────────────────────────────────────
# Setup runner
# ─────────────────────────────────────────────────────────────────────────────

class SetupRunner:
    """
    Provisions the wow-server directory and pulls Docker images.
    Designed to run in a background thread.
    log_fn(message, level) streams progress to the log panel.
    progress_fn(step_index, total, step_name) updates the setup step rows.

    Server-type awareness
    ─────────────────────
    • "base"       → docker-compose.yml          (vanilla AzerothCore)
    • "npcbots"    → docker-compose-npcbots.yml  (trickerer NPCBots fork)
    • "playerbots" → docker-compose-playerbots.yml (liyunfan1223 fork)

    For bot types, also copies the eluna/ Lua scripts and writes a .env file
    so docker-compose picks up the bot count/faction settings from config.
    """

    # Map server type → bundled compose filename
    _COMPOSE_FILES = {
        "base":       "docker-compose.yml",
        "npcbots":    "docker-compose-npcbots.yml",
        "playerbots": "docker-compose-playerbots.yml",
    }

    def __init__(self, log_fn: LogFn) -> None:
        self.log_fn = log_fn
        cfg = config.load()
        self.server_type = cfg.get("server_type", "base")
        self._cfg = cfg
        paths = cfg.get("server_paths", config.DEFAULTS["server_paths"])
        self.server_path = Path(paths.get(self.server_type, paths["base"]))

        # Bundled server assets sit in ../server/ relative to this file
        self._server_assets = Path(__file__).parent.parent / "server"

        compose_name = self._COMPOSE_FILES.get(self.server_type, "docker-compose.yml")
        self.compose_src = self._server_assets / compose_name

    @property
    def step_names(self) -> list:
        if self.server_type == "playerbots":
            image_step = "Build Playerbots image (20–40 min)"
        else:
            image_step = "Pull Docker images"
        base = [
            "Create server directory",
            "Copy docker-compose.yml",
            "Write bot .env config",
            image_step,
        ]
        if self.server_type in ("npcbots", "playerbots"):
            base.insert(2, "Copy Eluna Lua scripts")
        return base

    def run_all(self, progress_fn: Optional[Callable] = None) -> bool:
        steps: list = [
            self._create_dirs,
            self._copy_compose,
        ]
        if self.server_type in ("npcbots", "playerbots"):
            steps.append(self._copy_eluna_scripts)
        steps += [
            self._write_env_file,
            self._pull_images,
        ]

        total = len(steps)
        names = self.step_names
        for i, fn in enumerate(steps):
            name = names[i]
            self.log_fn(f"[{i + 1}/{total}] {name}...", "INFO")
            if progress_fn:
                progress_fn(i, total, name)
            ok, msg = fn()
            level = "INFO" if ok else "ERROR"
            icon = "✅" if ok else "❌"
            self.log_fn(f"    {icon} {msg}", level)
            if progress_fn:
                progress_fn(i + 1, total, name, ok)
            if not ok:
                return False
        self.log_fn("Setup complete! All steps finished successfully. ✅", "INFO")
        return True

    def _create_dirs(self) -> Tuple[bool, str]:
        try:
            (self.server_path / "logs").mkdir(parents=True, exist_ok=True)
            if self.server_type in ("npcbots", "playerbots"):
                (self.server_path / "eluna").mkdir(parents=True, exist_ok=True)
            return True, f"Created {self.server_path}"
        except OSError as e:
            return False, str(e)

    def _copy_compose(self) -> Tuple[bool, str]:
        dest = self.server_path / "docker-compose.yml"
        if not self.compose_src.exists():
            return False, f"Source not found: {self.compose_src}  (check Windows-DadsMMoLab/server/)"
        try:
            import shutil as _sh
            _sh.copy2(str(self.compose_src), str(dest))
            label = self._COMPOSE_FILES.get(self.server_type, "docker-compose.yml")
            copied = [label]

            # For types that use a local build, also copy the Dockerfile and
            # any companion files (entrypoint scripts, etc.) so that
            # docker compose build can find them in the server directory.
            for extra_name in [
                f"Dockerfile.{self.server_type}",
                f"entrypoint-{self.server_type}.sh",
            ]:
                extra_src = self._server_assets / extra_name
                if extra_src.exists():
                    _sh.copy2(str(extra_src), str(self.server_path / extra_name))
                    copied.append(extra_name)

            return True, f"Copied {', '.join(copied)} → {self.server_path}"
        except OSError as e:
            return False, str(e)

    def _copy_eluna_scripts(self) -> Tuple[bool, str]:
        """Copy bundled eluna/*.lua scripts into the server's eluna/ directory."""
        src_dir = self._server_assets / "eluna"
        dst_dir = self.server_path / "eluna"
        dst_dir.mkdir(parents=True, exist_ok=True)

        if not src_dir.exists():
            return True, "No eluna/ source directory found — skipped"

        import shutil as _sh
        copied = 0
        for lua_file in src_dir.glob("*.lua"):
            _sh.copy2(str(lua_file), str(dst_dir / lua_file.name))
            copied += 1

        if copied == 0:
            return True, "No .lua scripts found in eluna/ — skipped"
        return True, f"Copied {copied} Lua script(s) → {dst_dir}"

    def _write_env_file(self) -> Tuple[bool, str]:
        """
        Write a .env file alongside docker-compose.yml so compose picks up
        bot count / faction settings from the launcher config.
        For base servers, writes an empty .env (no-op).
        """
        env_path = self.server_path / ".env"
        lines: list = [
            "# Auto-generated by Dad's MMO Lab Launcher — do not edit manually.",
            "# Re-run Setup to update these values after changing Bot Settings.",
            "",
        ]

        if self.server_type == "npcbots":
            world_count    = self._cfg.get("npcbot_world_count",    40)
            faction_chance = self._cfg.get("npcbot_faction_chance", 500)
            lines += [
                "# ── NPCBots ──────────────────────────────────────────────────",
                f"NPCBOT_WORLD_COUNT={world_count}",
                f"NPCBOT_FACTION_CHANCE={faction_chance}",
                "",
            ]

        elif self.server_type == "playerbots":
            total    = self._cfg.get("playerbot_total_count",    50)
            alliance = self._cfg.get("playerbot_alliance_count", 25)
            horde    = self._cfg.get("playerbot_horde_count",    25)
            ah_buyer  = 1 if self._cfg.get("playerbot_ah_buyer",  True) else 0
            ah_seller = 1 if self._cfg.get("playerbot_ah_seller", True) else 0
            lines += [
                "# ── Playerbots ───────────────────────────────────────────────",
                f"PLAYERBOT_TOTAL_COUNT={total}",
                f"PLAYERBOT_ALLIANCE_COUNT={alliance}",
                f"PLAYERBOT_HORDE_COUNT={horde}",
                f"PLAYERBOT_AH_BUYER={ah_buyer}",
                f"PLAYERBOT_AH_SELLER={ah_seller}",
                "",
            ]

        try:
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return True, f"Wrote .env → {env_path}"
        except OSError as e:
            return False, str(e)

    def _create_configs(self) -> Tuple[bool, str]:
        # Config files are intentionally NOT pre-created.
        # The AzerothCore image ships valid defaults; mounting empty files causes
        # "Config::LoadFile: Empty file" crashes on startup.
        # DB connections are injected via environment variables in docker-compose.yml.
        logs_dir = self.server_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return True, "Skipped — container uses built-in defaults (DB via env vars)"

    def _pull_images(self) -> Tuple[bool, str]:
        # Playerbots has no public pre-built image — compile from source.
        # All other server types pull pre-built images from registries.
        if self.server_type == "playerbots":
            return self._build_images()
        return self._pull_images_from_registry()

    def _pull_images_from_registry(self) -> Tuple[bool, str]:
        self.log_fn("    docker compose pull — downloading images (may take 5–20 min on first run)...", "INFO")
        try:
            proc = subprocess.Popen(
                ["docker", "compose", "pull"],
                cwd=str(self.server_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in proc.stdout:
                stripped = line.rstrip()
                if stripped:
                    self.log_fn(f"    {stripped}", "INFO")
            proc.wait()
            if proc.returncode == 0:
                return True, "All Docker images pulled successfully"
            return False, f"docker compose pull exited {proc.returncode}"
        except FileNotFoundError:
            return False, "docker command not found — install Docker Desktop first"
        except Exception as exc:
            return False, str(exc)

    def _build_images(self) -> Tuple[bool, str]:
        self.log_fn(
            "    docker compose build — compiling Playerbots from source.\n"
            "    ⚠  First build takes 20–40 min while Docker compiles the server.\n"
            "    Subsequent starts use the cached image and are instant.",
            "INFO",
        )
        try:
            proc = subprocess.Popen(
                ["docker", "compose", "--progress=plain", "build"],
                cwd=str(self.server_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in proc.stdout:
                stripped = line.rstrip()
                if stripped:
                    self.log_fn(f"    {stripped}", "INFO")
            proc.wait()
            if proc.returncode == 0:
                return True, "Playerbots image built successfully"
            return False, f"docker compose build exited {proc.returncode}"
        except FileNotFoundError:
            return False, "docker command not found — install Docker Desktop first"
        except Exception as exc:
            return False, str(exc)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helper
# ─────────────────────────────────────────────────────────────────────────────

def _run(cmd: list, timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        result = subprocess.CompletedProcess(cmd, returncode=127)
        result.stdout = ""
        result.stderr = f"{cmd[0]}: command not found"
        return result
