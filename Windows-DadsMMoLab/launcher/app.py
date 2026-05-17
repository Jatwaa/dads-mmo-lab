"""
Dad's MMO Lab — Windows Launcher UI (merged pre-launch + launcher)
Built with CustomTkinter (dark theme, Windows 11 native feel).

Layout:
  ┌────────────────────────────────────────────────────────────────────┐
  │  Header (⚔ title + YouTube)                                        │
  ├────────────────────────────────────────────────────────────────────┤
  │  Toolbar: [👤 Accounts] [🔧 Patch] [🧙 Char Ed] [🗄 SQL] [🗂 Nav] │
  ├──────────────────────────────┬─────────────────────────────────────┤
  │  Setup Panel (left)          │  Launch Panel (right)               │
  │  • System Requirements       │  • Server type / paths              │
  │  • Server Setup steps        │  • Status banner                    │
  │                              │  • ⚔ Start & Play                   │
  ├──────────────────────────────┴─────────────────────────────────────┤
  │  Live log                                           [Copy] [Clear] │
  └────────────────────────────────────────────────────────────────────┘
"""
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk
import tkinter.ttk as ttk

import account_manager as acct
import bot_manager
import character_editor as chared
import client_patcher
import config
import sql_console as sqlc
import table_navigator as tnav
import log_handler as log
from launcher_core import LauncherCore, State, STATE_LABELS, STATE_COLORS
from prereq_checker import (
    CHECK_FN, INSTALL_FN, CheckStatus,
    PrereqItem, SetupRunner, STATUS_COLOR, STATUS_ICON,
    build_prereq_list,
)

LAUNCHER_VERSION = "1.4.0"
LOG_POLL_MS   = 100
MAX_LOG_LINES = 2000

_PASSING = {CheckStatus.OK, CheckStatus.WARNING, CheckStatus.REBOOT_REQUIRED}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self, core: LauncherCore) -> None:
        super().__init__()
        self._core = core
        self._cfg  = config.load()

        # ── Prereq state ──────────────────────────────────────────────────────
        self._prereqs:     list = build_prereq_list()
        self._lock         = threading.Lock()
        self._row_widgets: dict = {}
        self._step_icons:  list = []
        self._busy         = False

        self.title(f"Dad's MMO Lab — Windows Launcher v{LAUNCHER_VERSION}")
        self.geometry("1080x820")
        self.minsize(940, 700)
        self.resizable(True, True)

        self._core.set_on_state_change(self._on_state_change)

        self._build_ui()
        self._apply_state(State.IDLE)
        self._schedule_log_poll()
        self._load_cache()

        log.log(f"Dad's MMO Lab Launcher v{LAUNCHER_VERSION} ready.")
        log.log(f"Config: {config.CONFIG_FILE}")

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=0)  # header
        self.grid_rowconfigure(1, weight=0)  # toolbar
        self.grid_rowconfigure(2, weight=3)  # middle
        self.grid_rowconfigure(3, weight=1)  # log
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_toolbar()
        self._build_middle()
        self._build_log_panel()

    # ── header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, corner_radius=0, fg_color="#1a1a2e", height=52)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hdr,
            text=f"  ⚔  Dad's MMO Lab — Windows Launcher  v{LAUNCHER_VERSION}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#c0a060", anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=12)

        ctk.CTkButton(
            hdr, text="YouTube", width=80, height=28,
            fg_color="#c00000", hover_color="#900000",
            command=lambda: webbrowser.open("https://youtube.com/@DadsMmoLab"),
        ).grid(row=0, column=1, padx=8, pady=12)

    # ── toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = ctk.CTkFrame(self, corner_radius=0, fg_color="#10101e", height=44)
        tb.grid(row=1, column=0, sticky="ew")
        tb.grid_propagate(False)

        buttons = [
            ("👤  Accounts",        self._open_account_manager,  "#3a2060", "#2a1050"),
            ("🔧  Patch Client",    self._open_client_patcher,   "#2a3a20", "#1a2a10"),
            ("🧙  Char. Editor",    self._open_character_editor, "#20303a", "#101f28"),
            ("🗄  MySQL Console",   self._open_sql_console,      "#2a2a3a", "#1a1a28"),
            ("🗂  Table Navigator", self._open_table_navigator,  "#1a2a3a", "#0f1f2a"),
            ("🤖  Bot Settings",    self._open_bot_config,       "#2a1a3a", "#1a0a28"),
        ]
        for i, (label, cmd, fg, hov) in enumerate(buttons):
            ctk.CTkButton(
                tb, text=label, height=30, width=130,
                font=ctk.CTkFont(size=11),
                fg_color=fg, hover_color=hov, command=cmd,
            ).grid(row=0, column=i, padx=(8 if i == 0 else 4, 4), pady=7)

    # ── middle ────────────────────────────────────────────────────────────────

    def _build_middle(self) -> None:
        mid = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        mid.grid(row=2, column=0, sticky="nsew")
        mid.grid_columnconfigure(0, weight=5, minsize=460)
        mid.grid_columnconfigure(1, weight=3, minsize=300)
        mid.grid_rowconfigure(0, weight=1)

        self._build_setup_panel(mid)
        self._build_launch_panel(mid)

    # ── setup panel (left) ────────────────────────────────────────────────────

    def _build_setup_panel(self, parent: ctk.CTkFrame) -> None:
        scroll = ctk.CTkScrollableFrame(parent, corner_radius=0, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=(12, 4), pady=8)
        scroll.grid_columnconfigure(0, weight=1)

        self._build_prereq_section(scroll)
        self._build_setup_section(scroll)

    def _build_prereq_section(self, parent) -> None:
        outer = ctk.CTkFrame(parent, corner_radius=8)
        outer.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        outer.grid_columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(outer, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        title_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(title_row, text="System Requirements",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, sticky="w")

        self._cache_lbl = ctk.CTkLabel(
            title_row, text="", font=ctk.CTkFont(size=11), text_color="#1a8c3a"
        )
        self._cache_lbl.grid(row=0, column=1, padx=(10, 0), sticky="w")

        self._btn_check_all = ctk.CTkButton(
            title_row, text="Check All", width=100, height=28,
            command=self._on_check_all,
        )
        self._btn_check_all.grid(row=0, column=2, padx=(6, 0))

        self._btn_fix_all = ctk.CTkButton(
            title_row, text="Fix All Missing", width=130, height=28,
            fg_color="#5c3a00", hover_color="#402800",
            command=self._on_fix_all, state="disabled",
        )
        self._btn_fix_all.grid(row=0, column=3, padx=(6, 0))

        rows_frame = ctk.CTkFrame(outer, fg_color="#1a1a1a", corner_radius=6)
        rows_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        rows_frame.grid_columnconfigure(2, weight=1)

        for i, item in enumerate(self._prereqs):
            self._build_prereq_row(rows_frame, i, item)

    def _build_prereq_row(self, parent, row_idx: int, item: PrereqItem) -> None:
        bg  = "#1a1a1a" if row_idx % 2 == 0 else "#202020"
        row = ctk.CTkFrame(parent, fg_color=bg, corner_radius=0, height=36)
        row.grid(row=row_idx, column=0, columnspan=4, sticky="ew")
        row.grid_propagate(False)
        row.grid_columnconfigure(2, weight=1)

        icon_lbl = ctk.CTkLabel(
            row, text=STATUS_ICON[CheckStatus.PENDING],
            font=ctk.CTkFont(size=14),
            text_color=STATUS_COLOR[CheckStatus.PENDING], width=28,
        )
        icon_lbl.grid(row=0, column=0, padx=(10, 4), pady=6)

        ctk.CTkLabel(
            row, text=item.name,
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w", width=150,
        ).grid(row=0, column=1, padx=(0, 8), pady=6, sticky="w")

        detail_lbl = ctk.CTkLabel(
            row, text=item.description,
            font=ctk.CTkFont(size=11), text_color="#909090", anchor="w",
        )
        detail_lbl.grid(row=0, column=2, padx=4, pady=6, sticky="ew")

        action_btn = ctk.CTkButton(
            row, text="Check", width=88, height=26,
            command=lambda k=item.key: self._on_check_one(k),
        )
        action_btn.grid(row=0, column=3, padx=(6, 10), pady=5)

        self._row_widgets[item.key] = {"icon": icon_lbl, "detail": detail_lbl, "btn": action_btn}

    def _build_setup_section(self, parent) -> None:
        outer = ctk.CTkFrame(parent, corner_radius=8)
        outer.grid(row=1, column=0, sticky="ew")
        outer.grid_columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(outer, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        title_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(title_row, text="Server Setup",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, sticky="w")

        self._btn_run_setup = ctk.CTkButton(
            title_row, text="▶  Run Setup", width=120, height=28,
            fg_color="#1a4a2a", hover_color="#103520",
            command=self._on_run_setup, state="disabled",
        )
        self._btn_run_setup.grid(row=0, column=1, padx=(6, 0))

        steps_frame = ctk.CTkFrame(outer, fg_color="#1a1a1a", corner_radius=6)
        steps_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        runner = SetupRunner(log.log)
        for i, name in enumerate(runner.step_names):
            step_row = ctk.CTkFrame(steps_frame, fg_color="transparent", height=30)
            step_row.pack(fill="x", padx=8, pady=2)

            icon_lbl = ctk.CTkLabel(
                step_row, text="○",
                font=ctk.CTkFont(size=13), text_color="#606060", width=24,
            )
            icon_lbl.pack(side="left")

            ctk.CTkLabel(
                step_row, text=f"{i + 1}.  {name}",
                font=ctk.CTkFont(size=12), text_color="#b0b0b0", anchor="w",
            ).pack(side="left", padx=(4, 0))

            self._step_icons.append(icon_lbl)

    # ── launch panel (right) ──────────────────────────────────────────────────

    def _build_launch_panel(self, parent: ctk.CTkFrame) -> None:
        right = ctk.CTkFrame(parent, corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 12), pady=8)
        right.grid_columnconfigure(0, weight=1)

        # ── Server type — all three options on one line ───────────────────────
        type_row = ctk.CTkFrame(right, fg_color="transparent")
        type_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))

        ctk.CTkLabel(type_row, text="Type:",
                     font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self._server_type_var = tk.StringVar(value=self._cfg.get("server_type", "base"))
        for label, value in [("Base WoW", "base"), ("NPCBots", "npcbots"), ("Playerbots", "playerbots")]:
            ctk.CTkRadioButton(
                type_row, text=label,
                variable=self._server_type_var, value=value,
                command=self._on_server_type_change,
            ).pack(side="left", padx=(0, 10))

        # ── Server path — label + path + button on one line ───────────────────
        path_row = ctk.CTkFrame(right, fg_color="transparent")
        path_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        path_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(path_row, text="Server:",
                     font=ctk.CTkFont(weight="bold"), width=54, anchor="w").grid(
            row=0, column=0, sticky="w")
        self._server_path_label = ctk.CTkLabel(
            path_row, text=self._current_server_path(),
            font=ctk.CTkFont(size=10), anchor="w", text_color="#a0a0a0",
        )
        self._server_path_label.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkButton(path_row, text="Change...", width=80, height=24,
                      command=self._browse_server_path).grid(row=0, column=2)

        # ── WoW.exe — label + path + button on one line ───────────────────────
        wow_row = ctk.CTkFrame(right, fg_color="transparent")
        wow_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        wow_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(wow_row, text="WoW.exe:",
                     font=ctk.CTkFont(weight="bold"), width=54, anchor="w").grid(
            row=0, column=0, sticky="w")
        self._wow_path_label = ctk.CTkLabel(
            wow_row, text=self._cfg.get("wow_exe_path") or "(not set)",
            font=ctk.CTkFont(size=10), anchor="w", text_color="#a0a0a0",
        )
        self._wow_path_label.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkButton(wow_row, text="Browse...", width=80, height=24,
                      command=self._browse_wow_exe).grid(row=0, column=2)

        # ── Separator ─────────────────────────────────────────────────────────
        ctk.CTkFrame(right, height=1, fg_color="#303030").grid(
            row=3, column=0, sticky="ew", padx=12, pady=(0, 8))

        # ── Status banner ─────────────────────────────────────────────────────
        self._status_frame = ctk.CTkFrame(right, corner_radius=6, fg_color="#3a3a3a")
        self._status_frame.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 6))
        self._status_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self._status_frame,
                     text="════════════════════════════",
                     font=ctk.CTkFont(size=11), text_color="#606060").grid(row=0, column=0, pady=(6, 0))
        self._status_label = ctk.CTkLabel(
            self._status_frame, text=STATE_LABELS[State.IDLE],
            font=ctk.CTkFont(size=15, weight="bold"), text_color="#c0c0c0",
        )
        self._status_label.grid(row=1, column=0, pady=4)
        ctk.CTkLabel(self._status_frame,
                     text="════════════════════════════",
                     font=ctk.CTkFont(size=11), text_color="#606060").grid(row=2, column=0, pady=(0, 6))

        # ── Readiness ─────────────────────────────────────────────────────────
        ready_frame = ctk.CTkFrame(right, corner_radius=6, fg_color="#1e1e2a")
        ready_frame.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 8))
        ready_frame.grid_columnconfigure(0, weight=1)
        self._ready_server_lbl = ctk.CTkLabel(
            ready_frame, text="", font=ctk.CTkFont(size=11), anchor="w"
        )
        self._ready_server_lbl.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 2))
        self._ready_wow_lbl = ctk.CTkLabel(
            ready_frame, text="", font=ctk.CTkFont(size=11), anchor="w"
        )
        self._ready_wow_lbl.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))
        self._refresh_readiness()

        # ── Primary action ────────────────────────────────────────────────────
        self._btn_play = ctk.CTkButton(
            right, text="⚔  Start & Play",
            height=52, font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#1a5c2a", hover_color="#145020",
            command=self._on_play,
        )
        self._btn_play.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 4))

        # ── Secondary actions ─────────────────────────────────────────────────
        sec = ctk.CTkFrame(right, fg_color="transparent")
        sec.grid(row=7, column=0, sticky="ew", padx=12, pady=(0, 12))
        sec.grid_columnconfigure(0, weight=1)
        sec.grid_columnconfigure(1, weight=1)

        self._btn_start = ctk.CTkButton(
            sec, text="▶  Start Only", height=34, font=ctk.CTkFont(size=12),
            fg_color="#2a4a2a", hover_color="#1e361e", command=self._on_start,
        )
        self._btn_start.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 4))

        self._btn_stop = ctk.CTkButton(
            sec, text="■  Stop", height=34, font=ctk.CTkFont(size=12),
            fg_color="#5c1a1a", hover_color="#401010", command=self._on_stop,
        )
        self._btn_stop.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 4))

        self._btn_launch = ctk.CTkButton(
            sec, text="⚔  Launch WoW", height=34, font=ctk.CTkFont(size=12),
            fg_color="#1a4060", hover_color="#103050", command=self._on_launch_wow,
        )
        self._btn_launch.grid(row=1, column=0, columnspan=2, sticky="ew")

    # ── log panel ─────────────────────────────────────────────────────────────

    def _build_log_panel(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 12))
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(frame, fg_color="transparent", height=32)
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))
        toolbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(toolbar, text="Live Log",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(toolbar, text="📋 Copy", width=70, height=24,
                      command=self._copy_log).grid(row=0, column=1, padx=(4, 0))
        ctk.CTkButton(toolbar, text="🗑 Clear", width=70, height=24,
                      fg_color="#5a3a00", hover_color="#402800",
                      command=self._clear_log).grid(row=0, column=2, padx=(4, 0))

        self._log_box = ctk.CTkTextbox(
            frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word", state="disabled",
            fg_color="#0d0d0d", text_color="#c8c8c8",
        )
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))

    # ─────────────────────────────────────────────────────────────────────────
    # Log polling
    # ─────────────────────────────────────────────────────────────────────────

    def _schedule_log_poll(self) -> None:
        self.after(LOG_POLL_MS, self._poll_log)

    def _poll_log(self) -> None:
        entries = list(log.drain_queue())
        if entries:
            self._log_box.configure(state="normal")
            for entry in entries:
                self._log_box.insert("end", entry + "\n")
            lines = int(self._log_box.index("end-1c").split(".")[0])
            if lines > MAX_LOG_LINES:
                self._log_box.delete("1.0", f"{lines - MAX_LOG_LINES + 1}.0")
            self._log_box.configure(state="disabled")
            self._log_box.see("end")
        self._schedule_log_poll()

    # ─────────────────────────────────────────────────────────────────────────
    # Prereq row helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_row(self, item: PrereqItem) -> None:
        self.after(0, lambda: self._apply_row(item))

    def _apply_row(self, item: PrereqItem) -> None:
        w = self._row_widgets.get(item.key)
        if not w:
            return
        w["icon"].configure(text=STATUS_ICON[item.status], text_color=STATUS_COLOR[item.status])
        w["detail"].configure(text=item.detail)

        if item.status == CheckStatus.PENDING:
            w["btn"].configure(text="Check", state="normal",
                               command=lambda k=item.key: self._on_check_one(k))
        elif item.status == CheckStatus.CHECKING:
            w["btn"].configure(text="...", state="disabled")
        elif item.status == CheckStatus.INSTALLING:
            w["btn"].configure(text="Installing...", state="disabled")
        elif item.status in _PASSING:
            w["btn"].configure(text="Re-check", state="normal",
                               command=lambda k=item.key: self._on_check_one(k))
        elif item.status in (CheckStatus.MISSING, CheckStatus.FAILED):
            if item.key == "server":
                w["btn"].configure(text="Run Setup ↓", state="normal",
                                   command=self._on_run_setup)
            elif item.key == "wow":
                w["btn"].configure(text="Browse...", state="normal",
                                   command=self._browse_wow_exe)
            elif item.key == "python":
                w["btn"].configure(text="python.org ↗", state="normal",
                                   command=lambda: messagebox.showinfo(
                                       "Python",
                                       "Download Python 3.11+ from https://www.python.org/downloads/\n"
                                       "Make sure to check 'Add Python to PATH'."))
            elif item.key == "winget":
                w["btn"].configure(text="Help ↗", state="normal",
                                   command=lambda: messagebox.showinfo(
                                       "winget",
                                       "winget ships with Windows 11.\n"
                                       "If missing, update via the Microsoft Store: 'App Installer'."))
            elif item.can_auto_install:
                w["btn"].configure(text="Install", state="normal",
                                   command=lambda k=item.key: self._on_install_one(k))
            else:
                w["btn"].configure(text="Manual", state="disabled")

        self._refresh_global_buttons()

    def _apply_step_row(self, idx: int, done: bool, failed: bool = False) -> None:
        if idx >= len(self._step_icons):
            return
        if failed:
            self._step_icons[idx].configure(text="❌", text_color="#8c1a1a")
        elif done:
            self._step_icons[idx].configure(text="✅", text_color="#1a8c3a")
        else:
            self._step_icons[idx].configure(text="⏳", text_color="#c08000")

    def _refresh_global_buttons(self) -> None:
        if self._busy:
            return
        can_fix = any(
            p.status in (CheckStatus.MISSING, CheckStatus.FAILED) and p.can_auto_install
            for p in self._prereqs
        )
        self._btn_fix_all.configure(state="normal" if can_fix else "disabled")
        docker_ok = next((p for p in self._prereqs if p.key == "docker"), None)
        core_ok   = docker_ok and docker_ok.status in _PASSING
        self._btn_run_setup.configure(state="normal" if core_ok else "disabled")

    # ─────────────────────────────────────────────────────────────────────────
    # Prereq button handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_check_all(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        log.log("─── Checking all prerequisites ───", "INFO")
        threading.Thread(target=self._check_all_worker, daemon=True).start()

    def _check_all_worker(self) -> None:
        for item in self._prereqs:
            self._run_single_check(item)
        log.log("─── All checks complete ───", "INFO")
        self._save_cache()
        self.after(0, lambda: self._set_busy(False))

    def _on_check_one(self, key: str) -> None:
        item = self._get_item(key)
        if not item or self._busy:
            return
        log.log(f"Checking {item.name}...", "INFO")
        threading.Thread(target=lambda: self._run_single_check(item), daemon=True).start()

    def _run_single_check(self, item: PrereqItem) -> None:
        item.status = CheckStatus.CHECKING
        item.detail = "Checking..."
        self._refresh_row(item)
        fn = CHECK_FN.get(item.key)
        if fn:
            try:
                status, detail = fn()
            except Exception as exc:
                status, detail = CheckStatus.FAILED, str(exc)
        else:
            status, detail = CheckStatus.WARNING, "No check function defined"
        item.status = status
        item.detail = detail
        log.log(f"  {STATUS_ICON[status]} {item.name}: {detail}", "INFO")
        self._refresh_row(item)

    def _on_fix_all(self) -> None:
        if self._busy:
            return
        to_fix = [p for p in self._prereqs
                  if p.status in (CheckStatus.MISSING, CheckStatus.FAILED) and p.can_auto_install]
        if not to_fix:
            return
        self._set_busy(True)
        log.log(f"─── Fixing {len(to_fix)} missing prerequisite(s) ───", "INFO")
        threading.Thread(target=lambda: self._fix_worker(to_fix), daemon=True).start()

    def _fix_worker(self, items: list) -> None:
        for item in items:
            self._run_single_install(item)
        log.log("─── Fix pass complete — re-checking all ───", "INFO")
        for item in self._prereqs:
            self._run_single_check(item)
        self.after(0, lambda: self._set_busy(False))

    def _on_install_one(self, key: str) -> None:
        item = self._get_item(key)
        if not item or self._busy:
            return
        self._set_busy(True)
        threading.Thread(target=lambda: self._install_and_recheck(item), daemon=True).start()

    def _install_and_recheck(self, item: PrereqItem) -> None:
        self._run_single_install(item)
        self._run_single_check(item)
        self.after(0, lambda: self._set_busy(False))

    def _run_single_install(self, item: PrereqItem) -> None:
        fn = INSTALL_FN.get(item.key)
        if not fn:
            return
        log.log(f"Installing {item.name}...", "INFO")
        item.status = CheckStatus.INSTALLING
        item.detail = "Installing..."
        self._refresh_row(item)
        try:
            ok, msg = fn(log.log)
            if ok:
                item.status = CheckStatus.WARNING
                item.detail = msg
                log.log(f"✅ {item.name}: {msg}", "INFO")
            else:
                item.status = CheckStatus.FAILED
                item.detail = msg
                log.log(f"❌ {item.name}: {msg}", "ERROR")
        except Exception as exc:
            item.status = CheckStatus.FAILED
            item.detail = str(exc)
            log.log(f"❌ {item.name} install error: {exc}", "ERROR")
        self._refresh_row(item)

    def _on_run_setup(self) -> None:
        if self._busy:
            return
        for icon_lbl in self._step_icons:
            icon_lbl.configure(text="○", text_color="#606060")
        self._set_busy(True)
        log.log("─── Running server setup ───", "INFO")
        threading.Thread(target=self._setup_worker, daemon=True).start()

    def _setup_worker(self) -> None:
        runner = SetupRunner(log.log)

        def progress(step_idx: int, _total: int, _name: str, success=None) -> None:
            if success is None:
                self.after(0, lambda i=step_idx: self._apply_step_row(i, done=False))
            else:
                self.after(0, lambda i=step_idx, ok=success: self._apply_step_row(i, done=ok, failed=not ok))

        ok = runner.run_all(progress_fn=progress)
        if ok:
            log.log("─── Setup finished — re-checking server folder ───", "INFO")
            server_item = self._get_item("server")
            if server_item:
                self._run_single_check(server_item)
        else:
            log.log("─── Setup encountered an error — check log above ───", "ERROR")
        self.after(0, lambda: self._set_busy(False))

    # ─────────────────────────────────────────────────────────────────────────
    # Cache helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _save_cache(self) -> None:
        results = [{"key": p.key, "status": p.status.name, "detail": p.detail}
                   for p in self._prereqs]
        config.save_prereq_cache(results)

    def _load_cache(self) -> None:
        results, checked_at = config.load_prereq_cache()
        if not results:
            log.log("No previous check results — click 'Check All' to begin.", "INFO")
            return
        status_map = {r["key"]: r for r in results}
        for item in self._prereqs:
            cached = status_map.get(item.key)
            if not cached:
                continue
            try:
                item.status = CheckStatus[cached["status"]]
            except KeyError:
                item.status = CheckStatus.PENDING
            item.detail = cached.get("detail", "")
        for item in self._prereqs:
            self._refresh_row(item)
        all_pass = all(p.status in _PASSING for p in self._prereqs if p.required)
        if all_pass:
            self._cache_lbl.configure(
                text=f"✅ All checks passed — {checked_at}", text_color="#1a8c3a"
            )
            log.log(f"Cached results loaded ({checked_at}) — all required checks passed.", "INFO")
        else:
            self._cache_lbl.configure(
                text=f"⚠️ Last check {checked_at} — some items need attention",
                text_color="#c07000",
            )
            log.log(f"Cached results loaded ({checked_at}) — some issues found.", "INFO")
        self._refresh_global_buttons()

    # ─────────────────────────────────────────────────────────────────────────
    # Busy flag
    # ─────────────────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._btn_check_all.configure(state=state)
        if not busy:
            self._refresh_global_buttons()
        else:
            self._btn_fix_all.configure(state="disabled")
            self._btn_run_setup.configure(state="disabled")

    def _get_item(self, key: str) -> Optional[PrereqItem]:
        return next((p for p in self._prereqs if p.key == key), None)

    # ─────────────────────────────────────────────────────────────────────────
    # State change (from LauncherCore)
    # ─────────────────────────────────────────────────────────────────────────

    def _on_state_change(self, new_state: State) -> None:
        self.after(0, lambda: self._apply_state(new_state))

    def _apply_state(self, state: State) -> None:
        label = STATE_LABELS.get(state, str(state))
        color = STATE_COLORS.get(state, "#3a3a3a")
        self._status_label.configure(text=label)
        self._status_frame.configure(fg_color=color)

        idle_or_error = state in (State.IDLE, State.ERROR)
        running       = state not in (State.IDLE, State.ERROR, State.SHUTTING_DOWN)
        can_launch    = state in (State.READY, State.WAITING_WOW)

        self._btn_play.configure(state="normal" if idle_or_error else "disabled")
        self._btn_start.configure(state="normal" if idle_or_error else "disabled")
        self._btn_stop.configure(state="normal" if running else "disabled")
        self._btn_launch.configure(state="normal" if can_launch else "disabled")

        radio_state = "normal" if idle_or_error else "disabled"
        for child in self.winfo_children():
            self._set_radio_state(child, radio_state)

    def _set_radio_state(self, widget, state: str) -> None:
        if isinstance(widget, ctk.CTkRadioButton):
            widget.configure(state=state)
        for child in widget.winfo_children():
            self._set_radio_state(child, state)

    # ─────────────────────────────────────────────────────────────────────────
    # Launch action handlers
    # ─────────────────────────────────────────────────────────────────────────

    def _on_play(self) -> None:
        self._core.reload_config()
        self._core.start(auto_launch=True)

    def _on_start(self) -> None:
        self._core.reload_config()
        self._core.start(auto_launch=False)

    def _on_stop(self) -> None:
        self._core.stop()

    def _on_launch_wow(self) -> None:
        self._core.launch_wow()

    def _refresh_readiness(self) -> None:
        server_path = self._current_server_path()
        server_ok   = Path(server_path).is_dir()
        wow_path    = self._cfg.get("wow_exe_path", "")
        wow_ok      = bool(wow_path) and Path(wow_path).exists()
        self._ready_server_lbl.configure(
            text=f"{'✅' if server_ok else '❌'}  Server: "
                 + (Path(server_path).name if server_ok else "not found"),
            text_color="#50c060" if server_ok else "#c06050",
        )
        self._ready_wow_lbl.configure(
            text=f"{'✅' if wow_ok else '❌'}  WoW.exe: "
                 + (Path(wow_path).name if wow_ok else "not set"),
            text_color="#50c060" if wow_ok else "#c06050",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Tool dialogs
    # ─────────────────────────────────────────────────────────────────────────

    def _open_account_manager(self)  -> None: AccountManagerDialog(self)
    def _open_client_patcher(self)   -> None: ClientPatcherDialog(self)
    def _open_character_editor(self) -> None: CharacterEditorDialog(self)
    def _open_sql_console(self)      -> None: SqlConsoleDialog(self)
    def _open_table_navigator(self)  -> None: TableNavigatorDialog(self)
    def _open_bot_config(self)       -> None: BotConfigDialog(self)

    # ─────────────────────────────────────────────────────────────────────────
    # Config helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _current_server_path(self) -> str:
        st    = self._server_type_var.get() if hasattr(self, "_server_type_var") \
                else self._cfg.get("server_type", "base")
        paths = self._cfg.get("server_paths", config.DEFAULTS["server_paths"])
        return paths.get(st, paths["base"])

    def _on_server_type_change(self) -> None:
        self._cfg["server_type"] = self._server_type_var.get()
        config.save(self._cfg)
        self._server_path_label.configure(text=self._current_server_path())
        self._refresh_readiness()
        log.log(f"Server type → {self._cfg['server_type']}")

    def _browse_server_path(self) -> None:
        current = self._current_server_path()
        chosen  = filedialog.askdirectory(
            title="Select wow-server folder",
            initialdir=current if Path(current).exists() else str(Path.home()),
        )
        if chosen:
            st = self._server_type_var.get()
            self._cfg["server_paths"][st] = chosen
            config.save(self._cfg)
            self._server_path_label.configure(text=chosen)
            self._refresh_readiness()
            log.log(f"Server path ({st}) → {chosen}")

    def _browse_wow_exe(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Locate WoW.exe",
            filetypes=[("WoW Executable", "Wow.exe"), ("Executable", "*.exe"), ("All files", "*.*")],
            initialdir=str(Path(self._cfg.get("wow_exe_path", "") or Path.home()).parent),
        )
        if chosen:
            self._cfg["wow_exe_path"] = chosen
            config.save(self._cfg)
            self._wow_path_label.configure(text=chosen)
            self._refresh_readiness()
            log.log(f"WoW.exe → {chosen}")
            wow_item = self._get_item("wow")
            if wow_item:
                threading.Thread(
                    target=lambda: self._run_single_check(wow_item), daemon=True
                ).start()

    # ─────────────────────────────────────────────────────────────────────────
    # Log helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _copy_log(self) -> None:
        self._log_box.configure(state="normal")
        content = self._log_box.get("1.0", "end")
        self._log_box.configure(state="disabled")
        self.clipboard_clear()
        self.clipboard_append(content)
        log.log("Log copied to clipboard.")

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        log.clear_log_file()
        log.log("Log cleared.")

    # ─────────────────────────────────────────────────────────────────────────
    # Window close
    # ─────────────────────────────────────────────────────────────────────────

    def on_close(self) -> None:
        if self._busy:
            answer = messagebox.askyesno(
                "Operation in progress",
                "A setup operation is still running.\nExit anyway?"
            )
            if not answer:
                return
        state = self._core.state
        if state not in (State.IDLE, State.ERROR):
            answer = messagebox.askyesno(
                "Server is running",
                "The WoW server is still running.\n\nStop the server and exit?",
            )
            if not answer:
                return
            self._core.stop()
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Bot Config Dialog
# ─────────────────────────────────────────────────────────────────────────────

class BotConfigDialog(ctk.CTkToplevel):
    """
    Bot configuration window — works for both NPCBots and Playerbots.

    • Shows current settings (world count, faction split, AH toggles).
    • Writes changes to config.json + the server's .env file on Apply.
    • Shows live bot status if the server is currently running.
    • For Base WoW, shows an informational message that bots aren't enabled.
    """

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self._cfg = config.load()
        self._server_type = self._cfg.get("server_type", "base")

        self.title("🤖  Bot Settings")
        self.geometry("520x580")
        self.resizable(False, True)
        self.lift()
        self.focus()
        self.grab_set()

        self._build_ui()
        self._refresh_status()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, corner_radius=8, fg_color="#1a1a2e")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        hdr.grid_columnconfigure(0, weight=1)

        type_labels = {
            "base":       "Base WoW  (no bots)",
            "npcbots":    "NPCBots  — wandering world bots",
            "playerbots": "Playerbots  — simulated player bots",
        }
        ctk.CTkLabel(
            hdr,
            text=type_labels.get(self._server_type, self._server_type),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#c0a060", anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            hdr,
            text="Changes take effect on the next  ▶ Start  (docker compose up).",
            font=ctk.CTkFont(size=11),
            text_color="#808080", anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))

        # ── Settings panel ────────────────────────────────────────────────────
        if self._server_type == "base":
            self._build_base_notice()
        elif self._server_type == "npcbots":
            self._build_npcbot_settings()
        elif self._server_type == "playerbots":
            self._build_playerbot_settings()

        # ── Live status ───────────────────────────────────────────────────────
        status_frame = ctk.CTkFrame(self, corner_radius=8)
        status_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        status_frame.grid_columnconfigure(0, weight=1)
        status_frame.grid_rowconfigure(1, weight=1)

        status_hdr = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        status_hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(status_hdr, text="Live Bot Status",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(status_hdr, text="⟳ Refresh", width=80, height=26,
                      command=self._refresh_status).grid(row=0, column=1)

        self._status_box = ctk.CTkTextbox(
            status_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#0d0d0d", text_color="#c8c8c8",
            state="disabled", height=120,
        )
        self._status_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        # ── Footer buttons ────────────────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        footer.grid_columnconfigure(0, weight=1)

        self._status_lbl = ctk.CTkLabel(
            footer, text="", font=ctk.CTkFont(size=11), text_color="#a0a0a0", anchor="w",
        )
        self._status_lbl.grid(row=0, column=0, sticky="w")

        if self._server_type != "base":
            ctk.CTkButton(
                footer, text="Apply & Save", width=120, height=32,
                fg_color="#1a5c2a", hover_color="#145020",
                command=self._on_apply,
            ).grid(row=0, column=1, padx=(8, 0))

        ctk.CTkButton(
            footer, text="Close", width=80, height=32,
            fg_color="#3a3a3a", hover_color="#505050",
            command=self.destroy,
        ).grid(row=0, column=2, padx=(8, 0))

    def _build_base_notice(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=8, fg_color="#1e1e1e")
        frame.grid(row=1, column=0, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(
            frame,
            text=(
                "The Base WoW server type does not include any bot systems.\n\n"
                "Switch to  NPCBots  for wandering world bots that roam zones,\n"
                "fight mobs, and can be hired as companions.\n\n"
                "Switch to  Playerbots  for simulated player-bots that quest,\n"
                "trade, and post items on the Auction House.\n\n"
                "Change the server type in the Launch panel, then re-run Setup."
            ),
            font=ctk.CTkFont(size=12),
            text_color="#a0a0a0", justify="left", anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=18)

    def _build_npcbot_settings(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="NPCBot Settings",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 6))

        # ── World bot count ───────────────────────────────────────────────────
        ctk.CTkLabel(frame, text="Wandering bots:", anchor="w", width=130).grid(
            row=1, column=0, sticky="w", padx=12, pady=6)

        self._npcbot_count_var = tk.IntVar(value=self._cfg.get("npcbot_world_count", 40))
        count_slider = ctk.CTkSlider(
            frame, from_=0, to=200, number_of_steps=200,
            variable=self._npcbot_count_var,
            command=lambda v: self._npcbot_count_lbl.configure(
                text=str(int(v))),
        )
        count_slider.grid(row=1, column=1, sticky="ew", padx=8, pady=6)

        self._npcbot_count_lbl = ctk.CTkLabel(
            frame, text=str(self._npcbot_count_var.get()), width=36, anchor="e"
        )
        self._npcbot_count_lbl.grid(row=1, column=2, padx=(0, 12), pady=6)

        # ── Faction split ─────────────────────────────────────────────────────
        ctk.CTkLabel(frame, text="Faction split:", anchor="w", width=130).grid(
            row=2, column=0, sticky="w", padx=12, pady=6)

        self._faction_var = tk.IntVar(value=self._cfg.get("npcbot_faction_chance", 500))
        faction_slider = ctk.CTkSlider(
            frame, from_=0, to=1000, number_of_steps=1000,
            variable=self._faction_var,
            command=lambda v: self._faction_lbl.configure(
                text=self._faction_label(int(v))),
        )
        faction_slider.grid(row=2, column=1, sticky="ew", padx=8, pady=6)

        self._faction_lbl = ctk.CTkLabel(
            frame, text=self._faction_label(self._faction_var.get()),
            width=80, anchor="e",
        )
        self._faction_lbl.grid(row=2, column=2, padx=(0, 12), pady=6)

        ctk.CTkLabel(
            frame,
            text="0 = all Alliance  ·  500 = equal split  ·  1000 = all Horde",
            font=ctk.CTkFont(size=10), text_color="#707070",
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 10))

    def _build_playerbot_settings(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Playerbot Settings",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 6))

        # ── Alliance count ────────────────────────────────────────────────────
        ctk.CTkLabel(frame, text="Alliance bots:", anchor="w", width=130).grid(
            row=1, column=0, sticky="w", padx=12, pady=4)

        self._pb_ally_var = tk.IntVar(value=self._cfg.get("playerbot_alliance_count", 25))
        ally_slider = ctk.CTkSlider(
            frame, from_=0, to=200, number_of_steps=200,
            variable=self._pb_ally_var,
            command=lambda v: (
                self._pb_ally_lbl.configure(text=str(int(v))),
                self._pb_total_var.set(int(self._pb_ally_var.get()) + int(self._pb_horde_var.get())),
                self._pb_total_lbl.configure(text=str(self._pb_total_var.get())),
            ),
        )
        ally_slider.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        self._pb_ally_lbl = ctk.CTkLabel(
            frame, text=str(self._pb_ally_var.get()), width=36, anchor="e"
        )
        self._pb_ally_lbl.grid(row=1, column=2, padx=(0, 12), pady=4)

        # ── Horde count ───────────────────────────────────────────────────────
        ctk.CTkLabel(frame, text="Horde bots:", anchor="w", width=130).grid(
            row=2, column=0, sticky="w", padx=12, pady=4)

        self._pb_horde_var = tk.IntVar(value=self._cfg.get("playerbot_horde_count", 25))
        horde_slider = ctk.CTkSlider(
            frame, from_=0, to=200, number_of_steps=200,
            variable=self._pb_horde_var,
            command=lambda v: (
                self._pb_horde_lbl.configure(text=str(int(v))),
                self._pb_total_var.set(int(self._pb_ally_var.get()) + int(self._pb_horde_var.get())),
                self._pb_total_lbl.configure(text=str(self._pb_total_var.get())),
            ),
        )
        horde_slider.grid(row=2, column=1, sticky="ew", padx=8, pady=4)
        self._pb_horde_lbl = ctk.CTkLabel(
            frame, text=str(self._pb_horde_var.get()), width=36, anchor="e"
        )
        self._pb_horde_lbl.grid(row=2, column=2, padx=(0, 12), pady=4)

        # ── Total (read-only computed display) ────────────────────────────────
        ctk.CTkLabel(frame, text="Total bots:", anchor="w", width=130,
                     font=ctk.CTkFont(weight="bold")).grid(
            row=3, column=0, sticky="w", padx=12, pady=4)

        init_total = self._cfg.get("playerbot_alliance_count", 25) + self._cfg.get("playerbot_horde_count", 25)
        self._pb_total_var = tk.IntVar(value=init_total)
        self._pb_total_lbl = ctk.CTkLabel(
            frame,
            text=str(init_total),
            font=ctk.CTkFont(weight="bold"),
            text_color="#c0a060",
        )
        self._pb_total_lbl.grid(row=3, column=1, sticky="w", padx=8, pady=4)

        # ── AH toggles ────────────────────────────────────────────────────────
        ctk.CTkFrame(frame, height=1, fg_color="#303030").grid(
            row=4, column=0, columnspan=3, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(frame, text="Auction House Bot",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=5, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 6))

        self._pb_ah_buyer_var = tk.BooleanVar(value=self._cfg.get("playerbot_ah_buyer", True))
        ctk.CTkCheckBox(
            frame, text="Bots bid on AH listings  (buyer)",
            variable=self._pb_ah_buyer_var,
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=12, pady=2)

        self._pb_ah_seller_var = tk.BooleanVar(value=self._cfg.get("playerbot_ah_seller", True))
        ctk.CTkCheckBox(
            frame, text="Bots list items for sale  (seller)",
            variable=self._pb_ah_seller_var,
        ).grid(row=7, column=0, columnspan=3, sticky="w", padx=12, pady=(2, 10))

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _faction_label(value: int) -> str:
        if value <= 50:
            return "All Alliance"
        if value >= 950:
            return "All Horde"
        ally_pct = int((1000 - value) / 10)
        horde_pct = 100 - ally_pct
        return f"{ally_pct}% A / {horde_pct}% H"

    # ── Status refresh ────────────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        self._status_box.configure(state="normal")
        self._status_box.delete("1.0", "end")
        self._status_box.insert("end", "Querying…")
        self._status_box.configure(state="disabled")
        threading.Thread(target=self._status_worker, daemon=True).start()

    def _status_worker(self) -> None:
        status = bot_manager.get_bot_status()
        self.after(0, lambda: self._show_status(status))

    def _show_status(self, status: dict) -> None:
        self._status_box.configure(state="normal")
        self._status_box.delete("1.0", "end")

        if "error" in status:
            self._status_box.insert("end", f"⚠  {status['error']}\n")
            self._status_box.insert("end", "\n(Start the server to see live counts.)")
        else:
            if self._server_type == "npcbots":
                self._status_box.insert("end",
                    f"Wandering bots  : {status.get('wandering_total', '?')}\n"
                    f"  Alliance       : {status.get('alliance', '?')}\n"
                    f"  Horde          : {status.get('horde', '?')}\n"
                )
            elif self._server_type == "playerbots":
                self._status_box.insert("end",
                    f"Total bots       : {status.get('total', '?')}\n"
                    f"  Alliance       : {status.get('alliance', '?')}\n"
                    f"  Horde          : {status.get('horde', '?')}\n"
                    f"AH bot listings  : {status.get('ah_listings', '?')}\n"
                )

        self._status_box.configure(state="disabled")

    # ── Apply ─────────────────────────────────────────────────────────────────

    def _on_apply(self) -> None:
        cfg = config.load()

        if self._server_type == "npcbots":
            cfg["npcbot_world_count"]    = int(self._npcbot_count_var.get())
            cfg["npcbot_faction_chance"] = int(self._faction_var.get())

        elif self._server_type == "playerbots":
            ally  = int(self._pb_ally_var.get())
            horde = int(self._pb_horde_var.get())
            cfg["playerbot_alliance_count"] = ally
            cfg["playerbot_horde_count"]    = horde
            cfg["playerbot_total_count"]    = ally + horde
            cfg["playerbot_ah_buyer"]       = bool(self._pb_ah_buyer_var.get())
            cfg["playerbot_ah_seller"]      = bool(self._pb_ah_seller_var.get())

        config.save(cfg)
        self._cfg = cfg

        # Write the .env file alongside the server's docker-compose.yml
        paths = cfg.get("server_paths", config.DEFAULTS["server_paths"])
        server_path = paths.get(self._server_type, paths["base"])
        ok, msg = bot_manager.write_env_file(server_path, cfg)

        if ok:
            self._set_status(f"✅ Saved — restart server to apply changes.", "#1a8c3a")
            log.log(f"Bot config applied: {msg}", "INFO")
        else:
            self._set_status(f"⚠ Config saved but .env write failed: {msg}", "#c07000")
            log.log(f"Bot .env write failed: {msg}", "ERROR")

    def _set_status(self, text: str, color: str = "#a0a0a0") -> None:
        self._status_lbl.configure(text=text, text_color=color)


# ─────────────────────────────────────────────────────────────────────────────
# Account Manager Dialog
# ─────────────────────────────────────────────────────────────────────────────

class AccountManagerDialog(ctk.CTkToplevel):
    """
    Modal-style window for creating and listing WoW accounts.
    Writes directly to the acore_auth database via docker exec.
    """

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.title("Account Manager")
        self.geometry("560x520")
        self.resizable(False, True)
        self.lift()
        self.focus()
        self.grab_set()   # modal

        self._build_ui()
        self._refresh_list()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_create_section()
        self._build_list_section()
        self._build_status_bar()

    def _build_create_section(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Create Account",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(10, 6)
        )

        ctk.CTkLabel(frame, text="Username", anchor="w").grid(
            row=1, column=0, sticky="w", padx=12, pady=4)
        self._username_var = tk.StringVar()
        ctk.CTkEntry(frame, textvariable=self._username_var, width=180).grid(
            row=1, column=1, sticky="w", padx=8, pady=4)

        ctk.CTkLabel(frame, text="Password", anchor="w").grid(
            row=2, column=0, sticky="w", padx=12, pady=4)
        self._password_var = tk.StringVar()
        ctk.CTkEntry(frame, textvariable=self._password_var, show="●", width=180).grid(
            row=2, column=1, sticky="w", padx=8, pady=4)

        ctk.CTkLabel(frame, text="GM Level", anchor="w").grid(
            row=3, column=0, sticky="w", padx=12, pady=4)
        self._gm_var = tk.StringVar(value="Player (0)")
        ctk.CTkOptionMenu(
            frame,
            values=list(acct.GM_LEVELS.keys()),
            variable=self._gm_var,
            width=180,
        ).grid(row=3, column=1, sticky="w", padx=8, pady=4)

        self._btn_create = ctk.CTkButton(
            frame, text="Create Account", width=140, height=32,
            fg_color="#1a5c2a", hover_color="#145020",
            command=self._on_create,
        )
        self._btn_create.grid(row=3, column=2, padx=(8, 12), pady=4)

        ctk.CTkLabel(
            frame,
            text="Username: letters, numbers, underscore, max 16 chars.  Password: min 6 chars.",
            font=ctk.CTkFont(size=10),
            text_color="#707070",
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 10))

    def _build_list_section(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        toolbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(toolbar, text="Existing Accounts",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w")

        ctk.CTkButton(toolbar, text="⟳ Refresh", width=80, height=26,
                      command=self._refresh_list).grid(row=0, column=1)

        self._list_box = ctk.CTkTextbox(
            frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled",
            fg_color="#0d0d0d",
            text_color="#c8c8c8",
        )
        self._list_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def _build_status_bar(self) -> None:
        self._status_lbl = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color="#a0a0a0"
        )
        self._status_lbl.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 8))

    # ── handlers ──────────────────────────────────────────────────────────────

    def _on_create(self) -> None:
        username = self._username_var.get().strip()
        password = self._password_var.get().strip()
        gm_level = acct.GM_LEVELS.get(self._gm_var.get(), 0)

        self._set_status("Creating account...", "#c08000")
        self._btn_create.configure(state="disabled")

        def worker() -> None:
            ok, msg = acct.create_account(username, password, gm_level)
            self.after(0, lambda: self._on_create_done(ok, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _on_create_done(self, ok: bool, msg: str) -> None:
        self._btn_create.configure(state="normal")
        color = "#1a8c3a" if ok else "#8c1a1a"
        self._set_status(("✅ " if ok else "❌ ") + msg, color)
        log.log(f"Account manager: {msg}", "INFO" if ok else "ERROR")
        if ok:
            self._username_var.set("")
            self._password_var.set("")
            self._refresh_list()

    def _refresh_list(self) -> None:
        self._set_status("Loading accounts...", "#606060")

        def worker() -> None:
            ok, rows = acct.list_accounts()
            self.after(0, lambda: self._populate_list(ok, rows))

        threading.Thread(target=worker, daemon=True).start()

    def _populate_list(self, ok: bool, rows: list) -> None:
        self._list_box.configure(state="normal")
        self._list_box.delete("1.0", "end")

        if not ok or not rows:
            msg = "No accounts found." if ok else "Could not reach database — is the server running?"
            self._list_box.insert("end", msg)
            self._set_status(msg, "#8c1a1a" if not ok else "#606060")
        else:
            header = f"{'ID':<6}{'USERNAME':<18}{'GM LEVEL':<12}{'JOINED'}\n"
            self._list_box.insert("end", header)
            self._list_box.insert("end", "─" * 60 + "\n")
            for r in rows:
                gm = r["gmlevel"]
                gm_label = f"{gm} ({['Player','Mod','GM','Admin','Console'][int(gm)]})" if gm.isdigit() and int(gm) <= 4 else gm
                line = f"{r['id']:<6}{r['username']:<18}{gm_label:<12}{r['joined']}\n"
                self._list_box.insert("end", line)
            self._set_status(f"{len(rows)} account(s) found.", "#1a8c3a")

        self._list_box.configure(state="disabled")

    def _set_status(self, msg: str, color: str = "#a0a0a0") -> None:
        self._status_lbl.configure(text=msg, text_color=color)


# ─────────────────────────────────────────────────────────────────────────────
# Client Patcher Dialog
# ─────────────────────────────────────────────────────────────────────────────

class ClientPatcherDialog(ctk.CTkToplevel):
    """
    Scans the WoW client for realmlist files and lets the user patch/restore them
    so the client connects to the local AzerothCore server (127.0.0.1).
    """

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.title("Client Patcher")
        self.geometry("620x500")
        self.resizable(True, True)
        self.lift()
        self.focus()
        self.grab_set()

        self._report: client_patcher.PatchReport | None = None
        self._row_widgets: list[dict] = []   # one dict per target row

        self._build_ui()
        self._do_scan()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_targets_frame()
        self._build_status_bar()

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, corner_radius=8)
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hdr,
            text="Patch the WoW client so it connects to your local server (127.0.0.1).",
            font=ctk.CTkFont(size=12),
            text_color="#a0a0a0",
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        btn_row = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 10))

        ctk.CTkButton(
            btn_row, text="⟳ Re-scan", width=90, height=28,
            command=self._do_scan,
        ).grid(row=0, column=0, padx=(4, 4))

        self._btn_patch_all = ctk.CTkButton(
            btn_row, text="⚡ Patch All", width=100, height=28,
            fg_color="#1a5c2a", hover_color="#145020",
            command=self._on_patch_all,
        )
        self._btn_patch_all.grid(row=0, column=1, padx=4)

        self._btn_restore_all = ctk.CTkButton(
            btn_row, text="↩ Restore All", width=110, height=28,
            fg_color="#5c3a1a", hover_color="#402810",
            command=self._on_restore_all,
        )
        self._btn_restore_all.grid(row=0, column=2, padx=4)

        self._wow_dir_lbl = ctk.CTkLabel(
            hdr, text="WoW directory: (scanning…)",
            font=ctk.CTkFont(size=10), text_color="#707070", anchor="w",
        )
        self._wow_dir_lbl.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 8))

    def _build_targets_frame(self) -> None:
        outer = ctk.CTkFrame(self, corner_radius=8)
        outer.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        self._targets_scroll = ctk.CTkScrollableFrame(outer, corner_radius=0, fg_color="transparent")
        self._targets_scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._targets_scroll.grid_columnconfigure(0, weight=1)
        self._targets_scroll.grid_columnconfigure(1, weight=1)

    def _build_status_bar(self) -> None:
        self._status_lbl = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color="#a0a0a0", anchor="w",
        )
        self._status_lbl.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 8))

    # ── scanning ──────────────────────────────────────────────────────────────

    def _do_scan(self) -> None:
        self._set_status("Scanning WoW install…", "#c08000")
        self._btn_patch_all.configure(state="disabled")
        self._btn_restore_all.configure(state="disabled")

        def worker() -> None:
            report = client_patcher.scan()
            self.after(0, lambda: self._on_scan_done(report))

        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_done(self, report: client_patcher.PatchReport) -> None:
        self._report = report
        self._row_widgets.clear()

        # Clear previous rows
        for widget in self._targets_scroll.winfo_children():
            widget.destroy()

        if report.wow_dir is None:
            self._set_status(
                "❌  WoW.exe not configured — set it in the main window first.", "#8c1a1a"
            )
            self._wow_dir_lbl.configure(text="WoW directory: not configured")
            return

        self._wow_dir_lbl.configure(text=f"WoW directory: {report.wow_dir}")

        if not report.targets:
            self._set_status("No patchable files found.", "#c08000")
            return

        # Column headers
        header_frame = ctk.CTkFrame(self._targets_scroll, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        header_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header_frame, text="Status", width=60,
                     font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=0, padx=(4, 8))
        ctk.CTkLabel(header_frame, text="File",
                     font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(header_frame, text="Current Realmlist",
                     font=ctk.CTkFont(weight="bold"), anchor="w", width=180).grid(row=0, column=2, padx=8)
        ctk.CTkLabel(header_frame, text="Actions",
                     font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=3, padx=(0, 4))

        for idx, target in enumerate(report.targets):
            self._build_target_row(idx + 1, target)

        all_patched = report.all_patched
        any_backup = any(t.has_backup for t in report.targets)
        self._btn_patch_all.configure(state="disabled" if all_patched else "normal")
        self._btn_restore_all.configure(state="normal" if any_backup else "disabled")

        patched_count = sum(1 for t in report.targets if t.is_patched)
        self._set_status(
            f"✅ All files patched." if all_patched
            else f"⚠  {patched_count}/{len(report.targets)} file(s) patched.",
            "#1a8c3a" if all_patched else "#c08000",
        )

    def _build_target_row(self, row_idx: int, target: client_patcher.PatchTarget) -> None:
        row_frame = ctk.CTkFrame(
            self._targets_scroll,
            corner_radius=6,
            fg_color="#1e2a1e" if target.is_patched else ("#2a1e1e" if target.exists else "#1e1e2a"),
        )
        row_frame.grid(row=row_idx, column=0, sticky="ew", pady=3)
        row_frame.grid_columnconfigure(1, weight=1)

        # Status icon
        icon = "✅" if target.is_patched else ("○" if not target.exists else "❌")
        ctk.CTkLabel(row_frame, text=icon, width=40, font=ctk.CTkFont(size=14)).grid(
            row=0, column=0, padx=(8, 4), pady=8,
        )

        # File label + realmlist
        info = ctk.CTkFrame(row_frame, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=4)
        info.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(info, text=target.label, anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, sticky="w")
        rl_text = target.current_realmlist or "(not set)"
        rl_color = "#1a8c3a" if target.is_patched else ("#a05010" if rl_text != "(not set)" else "#606060")
        ctk.CTkLabel(info, text=rl_text, anchor="w",
                     font=ctk.CTkFont(size=10), text_color=rl_color).grid(row=1, column=0, sticky="w")

        # Action buttons
        action_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        action_frame.grid(row=0, column=2, padx=(4, 8), pady=6)

        btn_patch = ctk.CTkButton(
            action_frame, text="Patch", width=64, height=26,
            fg_color="#1a5c2a" if not target.is_patched else "#2a2a2a",
            hover_color="#145020" if not target.is_patched else "#3a3a3a",
            state="normal" if not target.is_patched else "disabled",
            command=lambda t=target: self._on_patch_one(t),
        )
        btn_patch.grid(row=0, column=0, padx=(0, 4))

        btn_restore = ctk.CTkButton(
            action_frame, text="Restore", width=70, height=26,
            fg_color="#5c3a1a" if target.has_backup else "#2a2a2a",
            hover_color="#402810" if target.has_backup else "#3a3a3a",
            state="normal" if target.has_backup else "disabled",
            command=lambda t=target: self._on_restore_one(t),
        )
        btn_restore.grid(row=0, column=1)

        self._row_widgets.append({"target": target, "btn_patch": btn_patch, "btn_restore": btn_restore, "frame": row_frame})

    # ── patch / restore ───────────────────────────────────────────────────────

    def _on_patch_all(self) -> None:
        if self._report is None:
            return
        self._set_status("Patching all files…", "#c08000")
        self._btn_patch_all.configure(state="disabled")

        def worker() -> None:
            patched, errors = client_patcher.patch_all(self._report)
            self.after(0, lambda: self._finish_operation("patch_all", patched, errors))

        threading.Thread(target=worker, daemon=True).start()

    def _on_restore_all(self) -> None:
        if self._report is None:
            return
        self._set_status("Restoring all files…", "#c08000")
        self._btn_restore_all.configure(state="disabled")

        def worker() -> None:
            restored, errors = client_patcher.restore_all(self._report)
            self.after(0, lambda: self._finish_operation("restore_all", restored, errors))

        threading.Thread(target=worker, daemon=True).start()

    def _on_patch_one(self, target: client_patcher.PatchTarget) -> None:
        self._set_status(f"Patching {target.label}…", "#c08000")

        def worker() -> None:
            ok, msg = client_patcher.patch(target)
            self.after(0, lambda: self._finish_operation("patch_one", int(ok), [] if ok else [msg]))

        threading.Thread(target=worker, daemon=True).start()

    def _on_restore_one(self, target: client_patcher.PatchTarget) -> None:
        self._set_status(f"Restoring {target.label}…", "#c08000")

        def worker() -> None:
            ok, msg = client_patcher.restore(target)
            self.after(0, lambda: self._finish_operation("restore_one", int(ok), [] if ok else [msg]))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_operation(self, op: str, count: int, errors: list) -> None:
        if errors:
            self._set_status(f"❌  {'; '.join(errors)}", "#8c1a1a")
        else:
            verb = {"patch_all": "Patched", "restore_all": "Restored",
                    "patch_one": "Patched", "restore_one": "Restored"}.get(op, "Done")
            self._set_status(f"✅  {verb} {count} file(s).", "#1a8c3a")
        # Re-scan so all row states reflect the new file contents
        self._do_scan()

    def _set_status(self, msg: str, color: str = "#a0a0a0") -> None:
        self._status_lbl.configure(text=msg, text_color=color)


# ─────────────────────────────────────────────────────────────────────────────
# Character Editor Dialog
# ─────────────────────────────────────────────────────────────────────────────

class CharacterEditorDialog(ctk.CTkToplevel):
    """
    Two-panel dialog: left = scrollable character list, right = detail/edit form.
    Edits level, money (gold/silver/copper), XP, and rested XP bonus.
    Changes are written to acore_characters via docker exec mysql.
    """

    _ONLINE_COLOR  = "#1a8c3a"
    _OFFLINE_COLOR = "#606060"
    _SEL_COLOR     = "#1a3a5a"
    _ROW_COLOR     = "#1e1e2e"

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.title("Character Editor")
        self.geometry("960x620")
        self.minsize(800, 500)
        self.resizable(True, True)
        self.lift()
        self.focus()
        self.grab_set()

        self._chars:    list[chared.Character] = []
        self._selected: chared.Character | None = None
        self._original: dict = {}           # snapshot of DB values for Revert

        # God-mode / auto-heal state
        self._god_stop  = threading.Event()
        self._god_guid: int | None = None
        self._god_count = 0

        self._build_ui()
        self._load_characters()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=0, minsize=240)
        self.grid_columnconfigure(1, weight=1)

        self._build_list_panel()
        self._build_detail_panel()
        self._build_status_bar()

    # ── Left: character list ──────────────────────────────────────────────────

    def _build_list_panel(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        toolbar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(toolbar, text="Characters",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(toolbar, text="⟳", width=32, height=26,
                      command=self._load_characters).grid(row=0, column=1)

        self._char_scroll = ctk.CTkScrollableFrame(frame, corner_radius=0, fg_color="transparent")
        self._char_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        self._char_scroll.grid_columnconfigure(0, weight=1)

    def _populate_list(self) -> None:
        for w in self._char_scroll.winfo_children():
            w.destroy()

        for idx, char in enumerate(self._chars):
            self._build_list_row(idx, char)

    def _build_list_row(self, idx: int, char: chared.Character) -> None:
        selected = self._selected and self._selected.guid == char.guid
        bg = self._SEL_COLOR if selected else self._ROW_COLOR

        row = ctk.CTkFrame(self._char_scroll, corner_radius=6, fg_color=bg)
        row.grid(row=idx, column=0, sticky="ew", pady=2)
        row.grid_columnconfigure(1, weight=1)
        row.bind("<Button-1>", lambda e, c=char: self._select_char(c))

        icon_lbl = ctk.CTkLabel(row, text=char.class_icon, width=28,
                                  font=ctk.CTkFont(size=16))
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=(8, 4), pady=6)
        icon_lbl.bind("<Button-1>", lambda e, c=char: self._select_char(c))

        name_lbl = ctk.CTkLabel(row, text=char.name, anchor="w",
                                  font=ctk.CTkFont(size=12, weight="bold"))
        name_lbl.grid(row=0, column=1, sticky="w", padx=(0, 4))
        name_lbl.bind("<Button-1>", lambda e, c=char: self._select_char(c))

        sub = f"Lvl {char.level}  {char.race_name} {char.class_name}"
        sub_lbl = ctk.CTkLabel(row, text=sub, anchor="w",
                                 font=ctk.CTkFont(size=10), text_color="#909090")
        sub_lbl.grid(row=1, column=1, sticky="w", padx=(0, 4), pady=(0, 4))
        sub_lbl.bind("<Button-1>", lambda e, c=char: self._select_char(c))

        dot_color = self._ONLINE_COLOR if char.online else self._OFFLINE_COLOR
        dot = ctk.CTkLabel(row, text="●", width=18,
                            font=ctk.CTkFont(size=10), text_color=dot_color)
        dot.grid(row=0, column=2, padx=(0, 6))
        dot.bind("<Button-1>", lambda e, c=char: self._select_char(c))

    # ── Right: detail / edit panel ────────────────────────────────────────────

    def _build_detail_panel(self) -> None:
        self._detail_frame = ctk.CTkFrame(self, corner_radius=8)
        self._detail_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=12)
        self._detail_frame.grid_rowconfigure(0, weight=1)
        self._detail_frame.grid_columnconfigure(0, weight=1)

        self._placeholder = ctk.CTkLabel(
            self._detail_frame,
            text="← Select a character to edit",
            font=ctk.CTkFont(size=14),
            text_color="#505050",
        )
        self._placeholder.grid(row=0, column=0)

        self._editor_scroll = ctk.CTkScrollableFrame(
            self._detail_frame, corner_radius=0, fg_color="transparent"
        )

    def _show_editor(self, char: chared.Character) -> None:
        self._placeholder.grid_remove()
        self._editor_scroll.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        for w in self._editor_scroll.winfo_children():
            w.destroy()
        self._editor_scroll.grid_columnconfigure(0, weight=1)

        self._build_char_header(char)
        self._build_editable_fields(char)
        self._build_quick_actions(char)
        self._build_info_section(char)
        self._build_stats_section()
        self._build_action_buttons()

        if char.online:
            self._build_online_warning()

        self._load_stats(char.guid)

    def _build_char_header(self, char: chared.Character) -> None:
        hdr = ctk.CTkFrame(self._editor_scroll, corner_radius=8, fg_color="#16213e")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr, text=char.class_icon, font=ctk.CTkFont(size=30)).grid(
            row=0, column=0, rowspan=2, padx=(14, 8), pady=12,
        )
        ctk.CTkLabel(hdr, text=char.name,
                     font=ctk.CTkFont(size=18, weight="bold"),
                     anchor="w").grid(row=0, column=1, sticky="w", pady=(10, 0))

        faction_color = chared.FACTION_COLOR.get(char.faction, "#808080")
        sub = f"{char.race_name}  •  {char.class_name}  •  {char.faction}  •  Acc: {char.account_name}"
        ctk.CTkLabel(hdr, text=sub, font=ctk.CTkFont(size=11),
                     text_color=faction_color, anchor="w").grid(
            row=1, column=1, sticky="w", pady=(0, 10)
        )

        badge_text  = "🟢 Online" if char.online else "⚫ Offline"
        badge_color = self._ONLINE_COLOR if char.online else self._OFFLINE_COLOR
        ctk.CTkLabel(hdr, text=badge_text, font=ctk.CTkFont(size=11),
                     text_color=badge_color).grid(row=0, column=2, padx=(0, 14))

    def _build_editable_fields(self, char: chared.Character) -> None:
        frame = ctk.CTkFrame(self._editor_scroll, corner_radius=8)
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Edit Character",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=14, pady=(10, 8)
        )

        # Level
        ctk.CTkLabel(frame, text="Level", anchor="e", width=90).grid(
            row=1, column=0, sticky="e", padx=(14, 8), pady=6
        )
        self._level_var = tk.StringVar(value=str(char.level))
        ctk.CTkEntry(frame, textvariable=self._level_var, width=60,
                     justify="center").grid(row=1, column=1, sticky="w", pady=6)
        ctk.CTkLabel(frame, text=f"/ {chared.MAX_LEVEL}",
                     text_color="#707070").grid(row=1, column=2, sticky="w", padx=4)
        ctk.CTkButton(frame, text="Max (80)", width=86, height=26,
                      command=lambda: self._level_var.set("80")).grid(
            row=1, column=3, padx=(0, 14), pady=6
        )

        # Money
        ctk.CTkLabel(frame, text="Money", anchor="e", width=90).grid(
            row=2, column=0, sticky="e", padx=(14, 8), pady=6
        )
        money_row = ctk.CTkFrame(frame, fg_color="transparent")
        money_row.grid(row=2, column=1, columnspan=3, sticky="w", pady=6, padx=(0, 14))
        self._gold_var   = tk.StringVar(value=str(char.gold))
        self._silver_var = tk.StringVar(value=str(char.silver))
        self._copper_var = tk.StringVar(value=str(char.copper_remainder))
        for col, (var, label, color) in enumerate([
            (self._gold_var,   "🟡 Gold",   "#c0a000"),
            (self._silver_var, "⚪ Silver", "#b0b0b0"),
            (self._copper_var, "🟤 Copper", "#a06020"),
        ]):
            ctk.CTkEntry(money_row, textvariable=var, width=68, justify="center").grid(
                row=0, column=col * 2, padx=(0, 2)
            )
            ctk.CTkLabel(money_row, text=label, font=ctk.CTkFont(size=10),
                         text_color=color).grid(row=0, column=col * 2 + 1, padx=(0, 12))

        # XP
        ctk.CTkLabel(frame, text="XP", anchor="e", width=90).grid(
            row=3, column=0, sticky="e", padx=(14, 8), pady=6
        )
        self._xp_var = tk.StringVar(value=str(char.xp))
        ctk.CTkEntry(frame, textvariable=self._xp_var, width=120,
                     justify="center").grid(row=3, column=1, sticky="w", pady=6)
        ctk.CTkButton(frame, text="Clear XP", width=86, height=26,
                      command=lambda: self._xp_var.set("0")).grid(
            row=3, column=3, padx=(0, 14), pady=6
        )

        # Rested XP
        ctk.CTkLabel(frame, text="Rested XP", anchor="e", width=90).grid(
            row=4, column=0, sticky="e", padx=(14, 8), pady=(6, 14)
        )
        self._rest_var = tk.StringVar(value=f"{char.rest_bonus:.1f}")
        ctk.CTkEntry(frame, textvariable=self._rest_var, width=120,
                     justify="center").grid(row=4, column=1, sticky="w", pady=(6, 14))
        ctk.CTkLabel(frame, text="(bonus XP from resting)",
                     font=ctk.CTkFont(size=10), text_color="#606060").grid(
            row=4, column=2, columnspan=2, sticky="w", padx=4, pady=(6, 14)
        )

    def _build_quick_actions(self, char: chared.Character) -> None:
        frame = ctk.CTkFrame(self._editor_scroll, corner_radius=8)
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        frame.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(frame, text="Quick Actions",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=14, pady=(10, 8)
        )

        # ── Health ────────────────────────────────────────────────────────────
        ctk.CTkButton(
            frame, text="❤  Set Max Health", width=150, height=30,
            fg_color="#5c1a1a", hover_color="#401010",
            command=lambda: self._on_set_max_health(char.guid),
        ).grid(row=1, column=0, padx=(14, 8), pady=(0, 8), sticky="w")

        is_active = self._god_guid == char.guid
        self._god_btn = ctk.CTkButton(
            frame,
            text="🔄  Auto-Heal: ON" if is_active else "🔄  Auto-Heal: OFF",
            width=160, height=30,
            fg_color="#1a5c1a" if is_active else "#2a2a2a",
            hover_color="#145014" if is_active else "#383838",
            command=lambda: self._toggle_god_mode(char.guid),
        )
        self._god_btn.grid(row=1, column=1, padx=(0, 8), pady=(0, 8), sticky="w")

        self._god_status_lbl = ctk.CTkLabel(
            frame,
            text=f"Active — healed {self._god_count}× so far" if is_active
                 else "Heals to max health every 3 s while active",
            font=ctk.CTkFont(size=10),
            text_color="#1a8c3a" if is_active else "#606060",
            anchor="w",
        )
        self._god_status_lbl.grid(row=1, column=2, sticky="w", padx=(0, 14), pady=(0, 8))

        # ── GM Role ───────────────────────────────────────────────────────────
        ctk.CTkFrame(frame, height=1, fg_color="#303030").grid(
            row=2, column=0, columnspan=4, sticky="ew", padx=14, pady=(2, 8)
        )

        ctk.CTkLabel(frame, text="👑  GM Role",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=3, column=0, sticky="w", padx=(14, 8), pady=(0, 4))

        # Current badge
        gm_color = "#c0a000" if char.gm_level > 0 else "#505050"
        ctk.CTkLabel(
            frame,
            text=f"Current: {char.gm_label} ({char.gm_level})",
            font=ctk.CTkFont(size=11),
            text_color=gm_color,
            anchor="w",
        ).grid(row=3, column=1, sticky="w", pady=(0, 4))

        # Dropdown — pre-select current level
        gm_option_labels = [label for label, _ in chared.GM_LEVEL_OPTIONS]
        current_label = next(
            (lbl for lbl, val in chared.GM_LEVEL_OPTIONS if val == char.gm_level),
            gm_option_labels[0],
        )
        self._gm_var = tk.StringVar(value=current_label)
        ctk.CTkOptionMenu(
            frame,
            variable=self._gm_var,
            values=gm_option_labels,
            width=150,
            fg_color="#2a2a3a",
            button_color="#3a3a5a",
            button_hover_color="#4a4a6a",
        ).grid(row=4, column=0, padx=(14, 8), pady=(0, 8), sticky="w")

        ctk.CTkButton(
            frame,
            text="Apply Role",
            width=100, height=30,
            fg_color="#4a3a00", hover_color="#382c00",
            command=lambda: self._on_set_gm_level(char),
        ).grid(row=4, column=1, padx=(0, 8), pady=(0, 8), sticky="w")

        ctk.CTkLabel(
            frame,
            text="Applies to account · relog required for effect",
            font=ctk.CTkFont(size=10),
            text_color="#505050",
            anchor="w",
        ).grid(row=4, column=2, sticky="w", padx=(0, 14), pady=(0, 8))

    def _build_info_section(self, char: chared.Character) -> None:
        frame = ctk.CTkFrame(self._editor_scroll, corner_radius=8)
        frame.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(frame, text="Character Info",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=14, pady=(10, 6)
        )

        info_rows = [
            ("GUID",      str(char.guid),
             "Health",    f"{char.health:,} / {char.max_health:,}"),
            ("Account",   char.account_name,
             "Play Time", char.play_time_str),
            ("Last Seen", char.last_seen_str,
             "Map / Zone", f"{char.map_id} / {char.zone}"),
            ("Position",  f"{char.pos_x:.1f},  {char.pos_y:.1f},  {char.pos_z:.1f}",
             "", ""),
        ]
        for ridx, (k1, v1, k2, v2) in enumerate(info_rows):
            r = ridx + 1
            pad_b = 12 if ridx == len(info_rows) - 1 else 4
            ctk.CTkLabel(frame, text=k1, anchor="e", width=80,
                         font=ctk.CTkFont(weight="bold"),
                         text_color="#808080").grid(
                row=r, column=0, sticky="e", padx=(14, 6), pady=(4, pad_b)
            )
            ctk.CTkLabel(frame, text=v1, anchor="w",
                         font=ctk.CTkFont(family="Consolas", size=11)).grid(
                row=r, column=1, sticky="w", pady=(4, pad_b)
            )
            if k2:
                ctk.CTkLabel(frame, text=k2, anchor="e", width=80,
                             font=ctk.CTkFont(weight="bold"),
                             text_color="#808080").grid(
                    row=r, column=2, sticky="e", padx=(14, 6), pady=(4, pad_b)
                )
                ctk.CTkLabel(frame, text=v2, anchor="w",
                             font=ctk.CTkFont(family="Consolas", size=11)).grid(
                    row=r, column=3, sticky="w", pady=(4, pad_b)
                )

    def _build_action_buttons(self) -> None:
        row = ctk.CTkFrame(self._editor_scroll, fg_color="transparent")
        row.grid(row=5, column=0, sticky="w", pady=(0, 8))

        self._btn_save = ctk.CTkButton(
            row, text="💾  Save Changes", width=140, height=36,
            fg_color="#1a5c2a", hover_color="#145020",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_save,
        )
        self._btn_save.grid(row=0, column=0, padx=(0, 8))

        ctk.CTkButton(
            row, text="↺  Revert", width=90, height=36,
            fg_color="#3a3a00", hover_color="#2a2a00",
            command=self._on_revert,
        ).grid(row=0, column=1)

    def _build_online_warning(self) -> None:
        warn = ctk.CTkFrame(self._editor_scroll, corner_radius=8, fg_color="#3a1a00")
        warn.grid(row=6, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(
            warn,
            text="⚠  This character is currently online. Changes will be written to the\n"
                 "   database but the server may overwrite them when the session ends.",
            font=ctk.CTkFont(size=11),
            text_color="#c08000",
            justify="left",
            anchor="w",
        ).grid(padx=14, pady=10, sticky="w")

    def _build_stats_section(self) -> None:
        frame = ctk.CTkFrame(self._editor_scroll, corner_radius=8)
        frame.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        frame.grid_columnconfigure((1, 3, 5), weight=1)

        ctk.CTkLabel(frame, text="Character Stats",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=6, sticky="w", padx=14, pady=(10, 6)
        )

        self._stat_labels: dict = {}

        def _row(r: int, c: int, key: str, label: str, suffix: str = "") -> None:
            key_lbl = ctk.CTkLabel(frame, text=label, anchor="e", width=100,
                                   font=ctk.CTkFont(weight="bold"),
                                   text_color="#808080")
            key_lbl.grid(row=r, column=c, sticky="e",
                         padx=(14 if c == 0 else 8, 4), pady=3)
            val_lbl = ctk.CTkLabel(frame, text="—",
                                   font=ctk.CTkFont(family="Consolas", size=11),
                                   anchor="w")
            val_lbl.grid(row=r, column=c + 1, sticky="w", padx=(0, 8), pady=3)
            self._stat_labels[key] = (val_lbl, suffix, key_lbl)

        # Primary stats (row 1)
        _row(1, 0, "strength",  "Strength")
        _row(1, 2, "agility",   "Agility")
        _row(1, 4, "stamina",   "Stamina")
        # row 2
        _row(2, 0, "intellect", "Intellect")
        _row(2, 2, "spirit",    "Spirit")
        _row(2, 4, "armor",     "Armor")
        # Health / primary power (row 3)
        _row(3, 0, "maxhealth", "Max Health")
        _row(3, 2, "maxpower",  "Max Power")   # filled per-class in _on_stats_loaded
        _row(3, 4, "resilience","Resilience",  "%")
        # Combat (row 4)
        _row(4, 0, "attackPower",        "Attack Power")
        _row(4, 2, "rangedAttackPower",  "Ranged AP")
        _row(4, 4, "spellPower",         "Spell Power")
        # Crit / avoidance (row 5)
        _row(5, 0, "critPct",        "Crit",        "%")
        _row(5, 2, "rangedCritPct",  "Ranged Crit", "%")
        _row(5, 4, "spellCritPct",   "Spell Crit",  "%")
        # Avoidance (row 6)
        _row(6, 0, "dodgePct",  "Dodge",  "%")
        _row(6, 2, "parryPct",  "Parry",  "%")
        _row(6, 4, "blockPct",  "Block",  "%")
        # Resistances (row 7)
        _row(7, 0, "resHoly",   "Holy Res")
        _row(7, 2, "resFire",   "Fire Res")
        _row(7, 4, "resNature", "Nature Res")
        # row 8
        _row(8, 0, "resFrost",  "Frost Res")
        _row(8, 2, "resShadow", "Shadow Res")
        _row(8, 4, "resArcane", "Arcane Res",)

        # Loading label placeholder
        self._stats_loading_lbl = ctk.CTkLabel(
            frame, text="Loading stats…",
            font=ctk.CTkFont(size=11), text_color="#606060",
        )
        self._stats_loading_lbl.grid(row=9, column=0, columnspan=6,
                                     sticky="w", padx=14, pady=(4, 10))

    def _load_stats(self, guid: int) -> None:
        def worker() -> None:
            ok, result = chared.get_stats(guid)
            self.after(0, lambda: self._on_stats_loaded(ok, result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_stats_loaded(self, ok: bool, result) -> None:
        if not hasattr(self, "_stat_labels"):
            return

        if hasattr(self, "_stats_loading_lbl"):
            if ok:
                self._stats_loading_lbl.configure(text="")
            else:
                self._stats_loading_lbl.configure(
                    text=f"Stats unavailable: {result}", text_color="#8c4a00"
                )

        if not ok:
            return

        cs: chared.CharacterStats = result
        char = self._selected

        power_label, power_val = cs.primary_power(char.cls if char else 0)

        values = {
            "strength":          cs.strength,
            "agility":           cs.agility,
            "stamina":           cs.stamina,
            "intellect":         cs.intellect,
            "spirit":            cs.spirit,
            "armor":             cs.armor,
            "maxhealth":         cs.maxhealth,
            "maxpower":          power_val,
            "resilience":        f"{cs.resilience:.1f}",
            "attackPower":       cs.attack_power,
            "rangedAttackPower": cs.ranged_attack_power,
            "spellPower":        cs.spell_power,
            "critPct":           f"{cs.crit_pct:.2f}",
            "rangedCritPct":     f"{cs.ranged_crit_pct:.2f}",
            "spellCritPct":      f"{cs.spell_crit_pct:.2f}",
            "dodgePct":          f"{cs.dodge_pct:.2f}",
            "parryPct":          f"{cs.parry_pct:.2f}",
            "blockPct":          f"{cs.block_pct:.2f}",
            "resHoly":           cs.res_holy,
            "resFire":           cs.res_fire,
            "resNature":         cs.res_nature,
            "resFrost":          cs.res_frost,
            "resShadow":         cs.res_shadow,
            "resArcane":         cs.res_arcane,
        }

        for key, (val_lbl, suffix, key_lbl) in self._stat_labels.items():
            if key == "maxpower":
                key_lbl.configure(text=power_label)
            raw = values.get(key, "—")
            if isinstance(raw, int):
                text = f"{raw:,}{suffix}"
            else:
                text = f"{raw}{suffix}"
            val_lbl.configure(text=text)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        self._status_lbl = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11),
            text_color="#a0a0a0", anchor="w",
        )
        self._status_lbl.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_characters(self) -> None:
        self._set_status("Loading characters…", "#c08000")

        def worker() -> None:
            ok, chars = chared.list_characters()
            self.after(0, lambda: self._on_loaded(ok, chars))

        threading.Thread(target=worker, daemon=True).start()

    def _on_loaded(self, ok: bool, result) -> None:
        if not ok:
            # result is the raw error string from _mysql
            self._set_status(f"❌  {result}", "#8c1a1a")
            return

        chars = result
        self._chars = chars
        prev_guid = self._selected.guid if self._selected else None
        self._selected = None

        self._populate_list()

        if prev_guid:
            match = next((c for c in chars if c.guid == prev_guid), None)
            if match:
                self._select_char(match)

        count  = len(chars)
        online = sum(1 for c in chars if c.online)
        self._set_status(
            f"{count} character(s) — {online} online." if count else "No characters found.",
            "#1a8c3a" if count else "#606060",
        )

    def _select_char(self, char: chared.Character) -> None:
        # Stop auto-heal when switching to a different character
        if self._god_guid is not None and self._god_guid != char.guid:
            self._stop_god_mode()

        self._selected = char
        self._original = {
            "level":      char.level,
            "gold":       char.gold,
            "silver":     char.silver,
            "copper":     char.copper_remainder,
            "xp":         char.xp,
            "rest_bonus": char.rest_bonus,
        }
        self._populate_list()
        self._show_editor(char)

    # ── Quick actions ─────────────────────────────────────────────────────────

    def _on_set_max_health(self, guid: int) -> None:
        char     = self._selected
        max_hp   = char.max_health if char else 0
        cls      = char.cls        if char else 0
        level    = char.level      if char else 1
        log.log(f"Set max health: guid={guid} known_max={max_hp} class={cls} level={level}", "INFO")
        self._set_status("Setting health to max…", "#c08000")

        def worker() -> None:
            ok, msg = chared.set_health_to_max(guid, max_hp, cls, level)
            def done():
                self._set_status(("✅  " if ok else "❌  ") + msg,
                                 "#1a8c3a" if ok else "#8c1a1a")
                if ok:
                    self._load_characters()
            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_set_gm_level(self, char: chared.Character) -> None:
        selected = self._gm_var.get()
        level = next(
            (val for lbl, val in chared.GM_LEVEL_OPTIONS if lbl == selected), 0
        )
        self._set_status(f"Setting GM role to {selected}…", "#c08000")

        def worker() -> None:
            ok, msg = chared.set_account_gm_level(char.account_name, level)
            def done():
                self._set_status(("✅  " if ok else "❌  ") + msg,
                                 "#1a8c3a" if ok else "#8c1a1a")
                if ok:
                    self._load_characters()
            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _toggle_god_mode(self, guid: int) -> None:
        if self._god_guid == guid:
            # Stop
            self._stop_god_mode()
        else:
            # Switch character if needed, then start
            self._stop_god_mode()
            self._start_god_mode(guid)

    def _start_god_mode(self, guid: int) -> None:
        self._god_stop.clear()
        self._god_guid  = guid
        self._god_count = 0
        char   = self._selected
        max_hp = char.max_health if char else 0
        cls    = char.cls        if char else 0
        level  = char.level      if char else 1
        self._update_god_ui(active=True)
        log.log(f"Character editor: auto-heal started for guid={guid} (max_hp={max_hp})", "INFO")

        def loop() -> None:
            while not self._god_stop.wait(3):   # 3-second interval
                ok, _ = chared.set_health_to_max(guid, max_hp, cls, level)
                if ok:
                    self._god_count += 1
                    self.after(0, self._refresh_god_status)

        threading.Thread(target=loop, daemon=True).start()

    def _stop_god_mode(self) -> None:
        if self._god_guid is not None:
            log.log(f"Character editor: auto-heal stopped for guid={self._god_guid} "
                    f"({self._god_count} heal(s) applied)", "INFO")
        self._god_stop.set()
        self._god_guid  = None
        self._god_count = 0
        self._update_god_ui(active=False)

    def _update_god_ui(self, active: bool) -> None:
        if not hasattr(self, "_god_btn"):
            return
        self._god_btn.configure(
            text="🔄  Auto-Heal: ON" if active else "🔄  Auto-Heal: OFF",
            fg_color="#1a5c1a" if active else "#2a2a2a",
            hover_color="#145014" if active else "#383838",
        )
        self._refresh_god_status()

    def _refresh_god_status(self) -> None:
        if not hasattr(self, "_god_status_lbl"):
            return
        active = self._god_guid is not None
        self._god_status_lbl.configure(
            text=f"Active — healed {self._god_count}× so far" if active
                 else "Heals to max health every 3 s while active",
            text_color="#1a8c3a" if active else "#606060",
        )

    def _on_close(self) -> None:
        self._stop_god_mode()
        self.destroy()

    # ── Save / Revert ─────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        if self._selected is None:
            return

        try:
            level = int(self._level_var.get())
        except ValueError:
            self._set_status("❌  Level must be a whole number.", "#8c1a1a")
            return

        try:
            gold   = max(0, int(self._gold_var.get()   or "0"))
            silver = max(0, min(99, int(self._silver_var.get() or "0")))
            copper = max(0, min(99, int(self._copper_var.get() or "0")))
        except ValueError:
            self._set_status("❌  Money values must be whole numbers.", "#8c1a1a")
            return
        money_copper = gold * 10000 + silver * 100 + copper

        try:
            xp = int(self._xp_var.get())
        except ValueError:
            self._set_status("❌  XP must be a whole number.", "#8c1a1a")
            return

        try:
            rest_bonus = float(self._rest_var.get())
        except ValueError:
            self._set_status("❌  Rested XP must be a number.", "#8c1a1a")
            return

        self._btn_save.configure(state="disabled")
        self._set_status("Saving…", "#c08000")
        guid = self._selected.guid

        def worker() -> None:
            ok, msg = chared.save_character(guid, level, money_copper, xp, rest_bonus)
            self.after(0, lambda: self._on_saved(ok, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _on_saved(self, ok: bool, msg: str) -> None:
        self._btn_save.configure(state="normal")
        self._set_status(("✅  " if ok else "❌  ") + msg,
                          "#1a8c3a" if ok else "#8c1a1a")
        if ok:
            self._load_characters()

    def _on_revert(self) -> None:
        if not self._original or self._selected is None:
            return
        self._level_var.set(str(self._original["level"]))
        self._gold_var.set(str(self._original["gold"]))
        self._silver_var.set(str(self._original["silver"]))
        self._copper_var.set(str(self._original["copper"]))
        self._xp_var.set(str(self._original["xp"]))
        self._rest_var.set(f"{self._original['rest_bonus']:.1f}")
        self._set_status("Reverted to last loaded values.", "#808080")

    def _set_status(self, msg: str, color: str = "#a0a0a0") -> None:
        self._status_lbl.configure(text=msg, text_color=color)


# ─────────────────────────────────────────────────────────────────────────────
# MySQL Console Dialog
# ─────────────────────────────────────────────────────────────────────────────

class SqlConsoleDialog(ctk.CTkToplevel):
    """
    A simple SQL query editor backed by docker exec mysql.
    SELECT/SHOW results render in a ttk.Treeview (scrollable table).
    INSERT/UPDATE/DELETE etc. report rows affected.
    Dangerous keywords (DROP, TRUNCATE, DELETE, ALTER) require confirmation.
    """

    # Common queries end-users would actually want
    _QUICK_QUERIES = [
        ("Characters",   "acore_characters",
         "SELECT guid, name, level, race, class, online FROM characters ORDER BY name;"),
        ("Accounts",     "acore_auth",
         "SELECT id, username, joindate, last_ip FROM account ORDER BY id;"),
        ("GM Levels",    "acore_auth",
         "SELECT a.username, aa.gmlevel, aa.RealmID "
         "FROM account a JOIN account_access aa ON a.id = aa.id ORDER BY aa.gmlevel DESC;"),
        ("Online Now",   "acore_characters",
         "SELECT name, level, race, class, zone FROM characters WHERE online=1;"),
        ("Show Tables",  "acore_characters",
         "SHOW TABLES;"),
        ("World Tables", "acore_world",
         "SHOW TABLES;"),
    ]

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.title("MySQL Console")
        self.geometry("1000x680")
        self.minsize(720, 500)
        self.resizable(True, True)
        self.lift()
        self.focus()
        self.grab_set()

        self._history: list[tuple[str, str]] = []   # (db, sql) pairs
        self._hist_idx = -1

        self._build_ui()
        self._apply_treeview_style()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_toolbar()
        self._build_editor()
        self._build_results()
        self._build_status_bar()

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, corner_radius=0, fg_color="#1a1a2e", height=44)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)

        ctk.CTkLabel(bar, text="Database:", font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, padx=(12, 4), pady=8
        )
        self._db_var = tk.StringVar(value=sqlc.DATABASES[0])
        ctk.CTkOptionMenu(
            bar, values=sqlc.DATABASES, variable=self._db_var, width=200,
        ).grid(row=0, column=1, pady=8)

        ctk.CTkButton(
            bar, text="▶  Execute", width=100, height=30,
            fg_color="#1a5c2a", hover_color="#145020",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_execute,
        ).grid(row=0, column=2, padx=12, pady=8)

        ctk.CTkButton(
            bar, text="📋 Copy Results", width=110, height=30,
            fg_color="#2a2a4a", hover_color="#1a1a38",
            command=self._copy_results,
        ).grid(row=0, column=3, pady=8)

        ctk.CTkButton(
            bar, text="🗑 Clear", width=70, height=30,
            fg_color="#3a2a00", hover_color="#2a1a00",
            command=self._clear_editor,
        ).grid(row=0, column=4, padx=(0, 8), pady=8)

        # Quick query buttons
        quick_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#111122")
        quick_frame.grid(row=1, column=0, sticky="ew")

        ctk.CTkLabel(quick_frame, text="Quick:", font=ctk.CTkFont(size=10),
                     text_color="#606060").grid(row=0, column=0, padx=(10, 4), pady=4)
        for col, (label, db, sql) in enumerate(self._QUICK_QUERIES, start=1):
            ctk.CTkButton(
                quick_frame, text=label,
                width=90, height=22,
                font=ctk.CTkFont(size=10),
                fg_color="#223",
                hover_color="#334",
                command=lambda d=db, s=sql: self._load_quick(d, s),
            ).grid(row=0, column=col, padx=3, pady=4)

    def _build_editor(self) -> None:
        editor_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#0d0d18", height=130)
        editor_frame.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
        editor_frame.grid_propagate(False)
        editor_frame.grid_rowconfigure(0, weight=1)
        editor_frame.grid_columnconfigure(0, weight=1)

        # Shift the query editor below the quick bar
        self.grid_rowconfigure(1, weight=0, minsize=170)

        self._sql_box = ctk.CTkTextbox(
            editor_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#0d0d18",
            text_color="#c8e0c8",
            wrap="none",
            height=120,
        )
        self._sql_box.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self._sql_box.bind("<Control-Return>", lambda e: self._on_execute())
        self._sql_box.bind("<Up>", self._history_up)
        self._sql_box.bind("<Down>", self._history_down)
        self._sql_box.insert("1.0", "SELECT * FROM characters LIMIT 25;")

        ctk.CTkLabel(
            editor_frame,
            text="Ctrl+Enter to run  •  ↑↓ for history",
            font=ctk.CTkFont(size=9),
            text_color="#404050",
            anchor="e",
        ).grid(row=1, column=0, sticky="e", padx=10, pady=(0, 4))

    def _build_results(self) -> None:
        results_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#0a0a14")
        results_frame.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)
        results_frame.grid_rowconfigure(0, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)

        # Treeview + scrollbars inside a plain tk.Frame (ttk needs tk parent)
        tree_container = tk.Frame(results_frame, bg="#0a0a14")
        tree_container.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        self._tree = ttk.Treeview(tree_container, style="Dark.Treeview",
                                   show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(tree_container, orient="vertical",
                             command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal",
                             command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Message label shown instead of treeview for non-SELECT results
        self._result_msg = ctk.CTkLabel(
            results_frame, text="", font=ctk.CTkFont(size=13),
            text_color="#a0a0a0",
        )

    def _build_status_bar(self) -> None:
        self._status_lbl = ctk.CTkLabel(
            self, text="Ready — enter a query above and press Ctrl+Enter or ▶ Execute",
            font=ctk.CTkFont(size=11), text_color="#606070", anchor="w",
        )
        self._status_lbl.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 6))

    # ── ttk dark theme ────────────────────────────────────────────────────────

    def _apply_treeview_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Dark.Treeview",
            background="#111122",
            foreground="#c8c8d8",
            fieldbackground="#111122",
            borderwidth=0,
            rowheight=22,
            font=("Consolas", 10),
        )
        style.configure(
            "Dark.Treeview.Heading",
            background="#1e1e34",
            foreground="#8080b0",
            borderwidth=1,
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Dark.Treeview",
                  background=[("selected", "#1a3a5a")],
                  foreground=[("selected", "#ffffff")])

    # ── execution ─────────────────────────────────────────────────────────────

    def _on_execute(self) -> None:
        sql = self._sql_box.get("1.0", "end").strip()
        db  = self._db_var.get()
        if not sql:
            return

        if sqlc.is_dangerous(sql):
            answer = messagebox.askyesno(
                "Dangerous Query",
                f"This query starts with a destructive keyword.\n\n{sql[:200]}\n\n"
                "Are you sure you want to run it?",
                parent=self,
            )
            if not answer:
                return

        self._set_status("Running…", "#c08000")
        self._clear_tree()

        def worker() -> None:
            result = sqlc.execute(sql, db)
            self.after(0, lambda: self._show_result(result, sql, db))

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, result: sqlc.QueryResult, sql: str, db: str) -> None:
        # Add to history
        self._history.append((db, sql))
        self._hist_idx = -1

        if not result.ok:
            self._show_message(f"❌  {result.error}")
            self._set_status(f"Error — {result.elapsed_ms:.0f} ms", "#8c1a1a")
            return

        if result.is_select:
            self._populate_tree(result)
            row_count = len(result.rows)
            cap_note  = f"  (showing first {sqlc.MAX_DISPLAY_ROWS})" if result.capped else ""
            self._set_status(
                f"✅  {row_count} row(s){cap_note} — {result.elapsed_ms:.0f} ms  [{db}]",
                "#1a8c3a",
            )
        else:
            self._show_message(f"✅  Query OK — {result.affected} row(s) affected")
            self._set_status(
                f"✅  {result.affected} row(s) affected — {result.elapsed_ms:.0f} ms  [{db}]",
                "#1a8c3a",
            )

    # ── tree population ───────────────────────────────────────────────────────

    def _populate_tree(self, result: sqlc.QueryResult) -> None:
        self._result_msg.grid_remove()
        self._tree.grid()

        self._tree["columns"] = result.columns
        for col in result.columns:
            self._tree.heading(col, text=col, anchor="w")
            # Auto-width: sample first 20 rows
            max_len = len(col)
            for row in result.rows[:20]:
                idx = result.columns.index(col)
                if idx < len(row):
                    max_len = max(max_len, len(str(row[idx])))
            width = min(max(max_len * 8 + 16, 60), 300)
            self._tree.column(col, width=width, anchor="w", stretch=False)

        for row in result.rows:
            # Pad short rows so they align with columns
            padded = list(row) + [""] * (len(result.columns) - len(row))
            self._tree.insert("", "end", values=padded)

    def _show_message(self, msg: str) -> None:
        self._clear_tree()
        self._result_msg.configure(text=msg)
        self._result_msg.grid(row=0, column=0)

    def _clear_tree(self) -> None:
        self._result_msg.grid_remove()
        self._tree.delete(*self._tree.get_children())
        self._tree["columns"] = []

    # ── toolbar actions ───────────────────────────────────────────────────────

    def _load_quick(self, db: str, sql: str) -> None:
        self._db_var.set(db)
        self._sql_box.delete("1.0", "end")
        self._sql_box.insert("1.0", sql)
        self._on_execute()

    def _clear_editor(self) -> None:
        self._sql_box.delete("1.0", "end")
        self._clear_tree()
        self._set_status("Cleared.", "#606070")

    def _copy_results(self) -> None:
        cols = self._tree["columns"]
        if not cols:
            return
        lines = ["\t".join(str(c) for c in cols)]
        for iid in self._tree.get_children():
            lines.append("\t".join(str(v) for v in self._tree.item(iid, "values")))
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self._set_status("Results copied to clipboard as TSV.", "#1a8c3a")

    # ── query history navigation ──────────────────────────────────────────────

    def _history_up(self, event) -> None:
        if not self._history:
            return
        self._hist_idx = max(0, (len(self._history) - 1
                                  if self._hist_idx == -1
                                  else self._hist_idx - 1))
        self._load_history()
        return "break"

    def _history_down(self, event) -> None:
        if not self._history or self._hist_idx == -1:
            return
        self._hist_idx = min(len(self._history) - 1, self._hist_idx + 1)
        self._load_history()
        return "break"

    def _load_history(self) -> None:
        if 0 <= self._hist_idx < len(self._history):
            db, sql = self._history[self._hist_idx]
            self._db_var.set(db)
            self._sql_box.delete("1.0", "end")
            self._sql_box.insert("1.0", sql)

    def _set_status(self, msg: str, color: str = "#606070") -> None:
        self._status_lbl.configure(text=msg, text_color=color)


# ─────────────────────────────────────────────────────────────────────────────
# Table Navigator Dialog
# ─────────────────────────────────────────────────────────────────────────────

class TableNavigatorDialog(ctk.CTkToplevel):
    """
    Three-panel database browser.

    Left:   expandable tree of databases → tables (click to select).
    Right:  CTkTabview with two tabs —
              📋 Structure  — DESCRIBE output (field / type / null / key / default / extra)
              📊 Data       — paginated SELECT * with optional WHERE filter
    Bottom: status bar + pagination controls.
    """

    _SEL_FG   = "#1a3a5a"
    _UNSEL_FG = "#16161e"
    _HDR_FG   = "#0e0e1a"

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.title("Table Navigator")
        self.geometry("1100x700")
        self.minsize(800, 520)
        self.resizable(True, True)
        self.lift()
        self.focus()
        self.grab_set()

        # State
        self._tables_map:  dict  = {}    # {db: [table, ...]}
        self._db_errors:   dict  = {}    # {db: error_string}
        self._expanded:    set   = set() # expanded db names
        self._selected_db: str   = ""
        self._sel_table:   str   = ""
        self._page:        int   = 0
        self._total_rows:  int   = 0
        self._page_size:   int   = tnav.PAGE_SIZES[0]
        self._where:       str   = ""

        self._build_ui()
        self._apply_tree_style()
        self._load_tables()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=0, minsize=220)
        self.grid_columnconfigure(1, weight=1)

        self._build_left()
        self._render_tree()       # show DB headers immediately while loading
        self._build_right()
        self._build_status_bar()

    # ── Left panel: database/table tree ──────────────────────────────────────

    def _build_left(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        toolbar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(toolbar, text="Databases",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(toolbar, text="⟳", width=30, height=26,
                      command=self._load_tables).grid(row=0, column=1)

        self._tree_scroll = ctk.CTkScrollableFrame(
            frame, corner_radius=0, fg_color="transparent"
        )
        self._tree_scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        self._tree_scroll.grid_columnconfigure(0, weight=1)

    def _render_tree(self) -> None:
        for w in self._tree_scroll.winfo_children():
            w.destroy()

        loading = not self._tables_map   # True before first load completes

        row_idx = 0
        for db in tnav.DATABASES:
            tables  = self._tables_map.get(db, [])
            err     = self._db_errors.get(db, "")
            expanded = db in self._expanded

            n_label = f"  ({len(tables)})" if tables else ""
            arrow   = "▼" if expanded else "▶"
            db_btn  = ctk.CTkButton(
                self._tree_scroll,
                text=f"{arrow}  {db}{n_label}",
                anchor="w",
                height=30,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=self._HDR_FG,
                hover_color="#1e1e2e",
                text_color="#8090c0",
                corner_radius=4,
                command=lambda d=db: self._toggle_db(d),
            )
            db_btn.grid(row=row_idx, column=0, sticky="ew", pady=(4, 1))
            row_idx += 1

            if expanded:
                if loading:
                    ctk.CTkLabel(
                        self._tree_scroll, text="  loading…",
                        font=ctk.CTkFont(size=10), text_color="#505060", anchor="w",
                    ).grid(row=row_idx, column=0, sticky="w", padx=8)
                    row_idx += 1
                elif err:
                    ctk.CTkLabel(
                        self._tree_scroll,
                        text=f"  ❌ {err[:60]}",
                        font=ctk.CTkFont(size=10), text_color="#8c2020",
                        anchor="w", wraplength=190,
                    ).grid(row=row_idx, column=0, sticky="w", padx=8, pady=2)
                    row_idx += 1
                elif not tables:
                    ctk.CTkLabel(
                        self._tree_scroll, text="  (no tables)",
                        font=ctk.CTkFont(size=10), text_color="#505060", anchor="w",
                    ).grid(row=row_idx, column=0, sticky="w", padx=8)
                    row_idx += 1
                for tbl in tables:
                    selected = (db == self._selected_db and tbl == self._sel_table)
                    tbl_btn  = ctk.CTkButton(
                        self._tree_scroll,
                        text=f"    {tbl}",
                        anchor="w",
                        height=26,
                        font=ctk.CTkFont(size=10),
                        fg_color=self._SEL_FG if selected else self._UNSEL_FG,
                        hover_color="#1e2e3e",
                        text_color="#d0d0e0" if selected else "#909090",
                        corner_radius=4,
                        command=lambda d=db, t=tbl: self._select_table(d, t),
                    )
                    tbl_btn.grid(row=row_idx, column=0, sticky="ew", pady=1)
                    row_idx += 1

    def _toggle_db(self, db: str) -> None:
        if db in self._expanded:
            self._expanded.discard(db)
        else:
            self._expanded.add(db)
        self._render_tree()

    def _select_table(self, db: str, table: str) -> None:
        self._selected_db = db
        self._sel_table   = table
        self._page        = 0
        self._total_rows  = 0
        self._where       = ""
        self._where_var.set("")
        self._render_tree()
        self._load_structure()
        self._load_data()

    # ── Right panel ───────────────────────────────────────────────────────────

    def _build_right(self) -> None:
        right = ctk.CTkFrame(self, corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=12)
        right.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(2, weight=0)
        right.grid_columnconfigure(0, weight=1)

        # Table header strip
        hdr = ctk.CTkFrame(right, corner_radius=0, fg_color="#0e0e1a", height=38)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)
        self._table_title = ctk.CTkLabel(
            hdr, text="← Select a table",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#7080a0", anchor="w",
        )
        self._table_title.grid(row=0, column=0, sticky="w", padx=14)
        self._row_count_lbl = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=11), text_color="#506070", anchor="e",
        )
        self._row_count_lbl.grid(row=0, column=1, sticky="e", padx=14)

        # Tabs
        self._tabs = ctk.CTkTabview(right, corner_radius=8)
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 0))
        self._tab_struct = self._tabs.add("📋  Structure")
        self._tab_data   = self._tabs.add("📊  Data")

        self._tab_struct.grid_rowconfigure(0, weight=1)
        self._tab_struct.grid_columnconfigure(0, weight=1)
        self._tab_data.grid_rowconfigure(0, weight=1)
        self._tab_data.grid_columnconfigure(0, weight=1)

        self._build_structure_tab()
        self._build_data_tab()
        self._build_pagination(right)

    def _build_structure_tab(self) -> None:
        container = tk.Frame(self._tab_struct, bg="#0a0a14")
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self._struct_tree = ttk.Treeview(
            container, style="Dark.Treeview", show="headings", selectmode="browse"
        )
        vsb = ttk.Scrollbar(container, orient="vertical",
                             command=self._struct_tree.yview)
        hsb = ttk.Scrollbar(container, orient="horizontal",
                             command=self._struct_tree.xview)
        self._struct_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._struct_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        cols = ("field", "type", "null", "key", "default", "extra")
        self._struct_tree["columns"] = cols
        widths = {"field": 160, "type": 160, "null": 60, "key": 60, "default": 120, "extra": 120}
        for col in cols:
            self._struct_tree.heading(col, text=col.upper(), anchor="w")
            self._struct_tree.column(col, width=widths[col], anchor="w", stretch=False)

    def _build_data_tab(self) -> None:
        container = tk.Frame(self._tab_data, bg="#0a0a14")
        container.grid(row=0, column=0, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self._data_tree = ttk.Treeview(
            container, style="Dark.Treeview", show="headings", selectmode="browse"
        )
        vsb = ttk.Scrollbar(container, orient="vertical",
                             command=self._data_tree.yview)
        hsb = ttk.Scrollbar(container, orient="horizontal",
                             command=self._data_tree.xview)
        self._data_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._data_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

    def _build_pagination(self, parent: ctk.CTkFrame) -> None:
        bar = ctk.CTkFrame(parent, corner_radius=0, fg_color="#0e0e1a", height=42)
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_propagate(False)

        # WHERE filter
        ctk.CTkLabel(bar, text="WHERE", font=ctk.CTkFont(size=10),
                     text_color="#606070").grid(row=0, column=0, padx=(12, 4), pady=8)
        self._where_var = tk.StringVar()
        ctk.CTkEntry(bar, textvariable=self._where_var, width=260,
                     placeholder_text="e.g.  level > 50   or   name LIKE 'Test%'",
                     font=ctk.CTkFont(family="Consolas", size=10),
                     height=26).grid(row=0, column=1, pady=8)
        ctk.CTkButton(bar, text="Apply", width=56, height=26,
                      command=self._apply_filter).grid(row=0, column=2, padx=(6, 16), pady=8)

        # Spacer
        ctk.CTkFrame(bar, fg_color="transparent", width=1).grid(row=0, column=3, sticky="ew")
        bar.grid_columnconfigure(3, weight=1)

        # Pagination
        self._btn_first = ctk.CTkButton(bar, text="◀◀", width=36, height=26,
                                         command=self._go_first)
        self._btn_first.grid(row=0, column=4, padx=2, pady=8)

        self._btn_prev = ctk.CTkButton(bar, text="◀", width=32, height=26,
                                        command=self._go_prev)
        self._btn_prev.grid(row=0, column=5, padx=2, pady=8)

        self._page_lbl = ctk.CTkLabel(bar, text="Page — / —",
                                       font=ctk.CTkFont(size=11), width=110)
        self._page_lbl.grid(row=0, column=6, padx=6)

        self._btn_next = ctk.CTkButton(bar, text="▶", width=32, height=26,
                                        command=self._go_next)
        self._btn_next.grid(row=0, column=7, padx=2, pady=8)

        self._btn_last = ctk.CTkButton(bar, text="▶▶", width=36, height=26,
                                        command=self._go_last)
        self._btn_last.grid(row=0, column=8, padx=(2, 8), pady=8)

        # Rows per page
        ctk.CTkLabel(bar, text="Rows:", font=ctk.CTkFont(size=10),
                     text_color="#606070").grid(row=0, column=9, padx=(8, 4), pady=8)
        self._page_size_var = tk.StringVar(value=str(self._page_size))
        ctk.CTkOptionMenu(
            bar,
            values=[str(n) for n in tnav.PAGE_SIZES],
            variable=self._page_size_var,
            width=70,
            command=self._on_page_size_change,
        ).grid(row=0, column=10, padx=(0, 12), pady=8)

    def _build_status_bar(self) -> None:
        self._status_lbl = ctk.CTkLabel(
            self, text="Loading databases…", font=ctk.CTkFont(size=11),
            text_color="#606070", anchor="w",
        )
        self._status_lbl.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))

    # ── ttk style (shared with SQL console) ──────────────────────────────────

    def _apply_tree_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Dark.Treeview",
                         background="#111122", foreground="#c8c8d8",
                         fieldbackground="#111122", borderwidth=0,
                         rowheight=22, font=("Consolas", 10))
        style.configure("Dark.Treeview.Heading",
                         background="#1e1e34", foreground="#8080b0",
                         borderwidth=1, relief="flat",
                         font=("Segoe UI", 9, "bold"))
        style.map("Dark.Treeview",
                  background=[("selected", "#1a3a5a")],
                  foreground=[("selected", "#ffffff")])

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_tables(self) -> None:
        self._set_status("Connecting to database…", "#c08000")
        # Reset to "loading" state so the tree shows spinners
        self._tables_map = {}
        self._db_errors  = {}
        self._render_tree()

        def worker() -> None:
            tables, errors = tnav.list_all_tables()
            self.after(0, lambda: self._on_tables_loaded(tables, errors))

        threading.Thread(target=worker, daemon=True).start()

    def _on_tables_loaded(self, tables: dict, errors: dict) -> None:
        self._tables_map = tables
        self._db_errors  = errors

        if tnav.DATABASES and not self._expanded:
            self._expanded.add(tnav.DATABASES[0])
        self._render_tree()

        if errors and all(db in errors for db in tnav.DATABASES):
            first_err = next(iter(errors.values()))
            self._set_status(f"❌  Cannot reach database — {first_err}", "#8c1a1a")
            return

        totals  = [f"{db}: {len(tbls)}" for db, tbls in tables.items() if tbls]
        summary = "  •  ".join(totals) if totals else "Connected — no tables found"
        self._set_status(summary, "#1a8c3a")

    def _load_structure(self) -> None:
        if not self._sel_table:
            return
        db, tbl = self._selected_db, self._sel_table
        self._set_status(f"Loading structure of {tbl}…", "#c08000")

        def worker() -> None:
            ok, cols = tnav.describe_table(tbl, db)
            self.after(0, lambda: self._on_structure(ok, cols, tbl))

        threading.Thread(target=worker, daemon=True).start()

    def _on_structure(self, ok: bool, cols: list, tbl: str) -> None:
        self._struct_tree.delete(*self._struct_tree.get_children())
        if not ok or not cols:
            self._set_status("Could not load structure.", "#8c1a1a")
            return
        for c in cols:
            self._struct_tree.insert(
                "", "end",
                values=(c["field"], c["type"], c["null"], c["key"], c["default"], c["extra"]),
            )
        self._set_status(f"{tbl}: {len(cols)} column(s)", "#1a8c3a")

    def _load_data(self) -> None:
        if not self._sel_table:
            return
        db, tbl = self._selected_db, self._sel_table
        offset = self._page * self._page_size
        self._set_status(f"Fetching rows {offset + 1}+…", "#c08000")
        self._update_pagination_buttons(enabled=False)

        def worker() -> None:
            ok_c, count  = tnav.row_count(tbl, db, self._where)
            ok_r, cols, rows = tnav.fetch_rows(tbl, db, self._page_size, offset, self._where)
            self.after(0, lambda: self._on_data(ok_c, count, ok_r, cols, rows, tbl))

        threading.Thread(target=worker, daemon=True).start()

    def _on_data(self, ok_c: bool, count: int, ok_r: bool, cols: list, rows: list, tbl: str) -> None:
        if ok_c:
            self._total_rows = count
            self._row_count_lbl.configure(text=f"{count:,} rows")

        self._data_tree.delete(*self._data_tree.get_children())

        if not ok_r:
            self._set_status("Failed to fetch rows.", "#8c1a1a")
            return

        # Rebuild columns
        self._data_tree["columns"] = cols
        for col in cols:
            self._data_tree.heading(col, text=col, anchor="w")
            max_w = len(col)
            for row in rows[:20]:
                idx = cols.index(col)
                if idx < len(row):
                    max_w = max(max_w, len(str(row[idx])))
            self._data_tree.column(
                col, width=min(max(max_w * 8 + 16, 60), 280), anchor="w", stretch=False
            )

        for row in rows:
            self._data_tree.insert("", "end", values=row)

        self._update_pagination_buttons(enabled=True)

        # Update title and page label
        total_pages = max(1, -(-self._total_rows // self._page_size))  # ceiling div
        self._page_lbl.configure(text=f"Page {self._page + 1} / {total_pages}")
        self._table_title.configure(
            text=f"{tbl}  ({self._selected_db})", text_color="#c0d0e0"
        )

        offset = self._page * self._page_size
        showing_to = min(offset + self._page_size, self._total_rows)
        where_note = f"  WHERE {self._where}" if self._where else ""
        self._set_status(
            f"Rows {offset + 1}–{showing_to} of {self._total_rows:,}{where_note}",
            "#1a8c3a",
        )

    # ── Pagination controls ───────────────────────────────────────────────────

    def _update_pagination_buttons(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        total_pages = max(1, -(-self._total_rows // self._page_size))
        first_dis = "disabled" if (not enabled or self._page == 0) else "normal"
        last_dis  = "disabled" if (not enabled or self._page >= total_pages - 1) else "normal"
        self._btn_first.configure(state=first_dis)
        self._btn_prev.configure(state=first_dis)
        self._btn_next.configure(state=last_dis)
        self._btn_last.configure(state=last_dis)

    def _go_first(self) -> None:
        self._page = 0
        self._load_data()

    def _go_last(self) -> None:
        total_pages = max(1, -(-self._total_rows // self._page_size))
        self._page = total_pages - 1
        self._load_data()

    def _go_prev(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._load_data()

    def _go_next(self) -> None:
        total_pages = max(1, -(-self._total_rows // self._page_size))
        if self._page < total_pages - 1:
            self._page += 1
            self._load_data()

    def _apply_filter(self) -> None:
        self._where = self._where_var.get().strip()
        self._page  = 0
        self._load_data()

    def _on_page_size_change(self, value: str) -> None:
        try:
            self._page_size = int(value)
        except ValueError:
            return
        self._page = 0
        if self._sel_table:
            self._load_data()

    def _set_status(self, msg: str, color: str = "#606070") -> None:
        if hasattr(self, "_status_lbl"):
            self._status_lbl.configure(text=msg, text_color=color)
