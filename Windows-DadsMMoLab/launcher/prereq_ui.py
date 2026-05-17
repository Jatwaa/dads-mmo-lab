"""
Dad's MMO Lab — Pre-Launch Setup Window

Flow:
  1. CHECK   — scan all prerequisites, show pass/fail per row
  2. FIX     — auto-install anything missing that supports it
  3. SETUP   — create server directory, copy compose file, pull Docker images
  4. LAUNCH  — open the main launcher window

All actions run in background threads; UI updates via after() callbacks.
All steps are streamed to the live log panel and written to the log file.
"""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

import config
import log_handler as log
from prereq_checker import (
    CHECK_FN, INSTALL_FN, CheckStatus,
    PrereqItem, SetupRunner, STATUS_COLOR, STATUS_ICON,
    build_prereq_list,
)

LOG_POLL_MS  = 100
MAX_LOG_LINES = 3000

# Which statuses count as "good enough to proceed"
_PASSING = {CheckStatus.OK, CheckStatus.WARNING, CheckStatus.REBOOT_REQUIRED}


class PrereqWindow(ctk.CTk):
    """
    Pre-launch prerequisite checker and server setup wizard.
    Sets self.should_launch = True when the user clicks "Open Launcher".
    """

    should_launch: bool = False

    def __init__(self) -> None:
        super().__init__()
        self.title("Dad's MMO Lab — Pre-Launch Setup")
        self.geometry("900x780")
        self.minsize(780, 620)

        self._prereqs: list = build_prereq_list()
        self._lock = threading.Lock()

        # Widget refs updated by background threads via after()
        self._row_widgets: dict = {}   # key → {icon_lbl, detail_lbl, action_btn}
        self._step_icons:  list = []   # [CTkLabel, ...]  one per setup step

        self._busy = False             # True while any background work is running

        self._build_ui()
        self._schedule_log_poll()
        self._load_cache()             # Restore last results, enable Launch if all passed

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=0)   # header
        self.grid_rowconfigure(1, weight=0)   # prereq section
        self.grid_rowconfigure(2, weight=0)   # setup section
        self.grid_rowconfigure(3, weight=1)   # log (expands)
        self.grid_rowconfigure(4, weight=0)   # footer
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_prereq_section()
        self._build_setup_section()
        self._build_log_section()
        self._build_footer()

    # ── header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, corner_radius=0, fg_color="#1a1a2e", height=52)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hdr,
            text="  ⚔  Dad's MMO Lab — Pre-Launch Setup",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#c0a060",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=12)

        # Phase breadcrumb
        ctk.CTkLabel(
            hdr,
            text="1. Check  →  2. Fix  →  3. Setup  →  4. Launch",
            font=ctk.CTkFont(size=11),
            text_color="#808080",
            anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=16, pady=12)

    # ── prereq section ────────────────────────────────────────────────────────

    def _build_prereq_section(self) -> None:
        outer = ctk.CTkFrame(self, corner_radius=8)
        outer.grid(row=1, column=0, sticky="ew", padx=12, pady=(10, 0))
        outer.grid_columnconfigure(0, weight=1)

        # Section title + controls
        title_row = ctk.CTkFrame(outer, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        title_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            title_row,
            text="System Requirements",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        # Cache status banner — hidden until cache is loaded
        self._cache_lbl = ctk.CTkLabel(
            title_row, text="",
            font=ctk.CTkFont(size=11),
            text_color="#1a8c3a",
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
            command=self._on_fix_all,
            state="disabled",
        )
        self._btn_fix_all.grid(row=0, column=3, padx=(6, 0))

        # Prereq rows
        rows_frame = ctk.CTkFrame(outer, fg_color="#1a1a1a", corner_radius=6)
        rows_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        rows_frame.grid_columnconfigure(1, weight=1)

        for i, item in enumerate(self._prereqs):
            self._build_prereq_row(rows_frame, i, item)

    def _build_prereq_row(self, parent: ctk.CTkFrame, row_idx: int, item: PrereqItem) -> None:
        bg = "#1a1a1a" if row_idx % 2 == 0 else "#202020"
        row = ctk.CTkFrame(parent, fg_color=bg, corner_radius=0, height=36)
        row.grid(row=row_idx, column=0, columnspan=4, sticky="ew")
        row.grid_propagate(False)
        row.grid_columnconfigure(2, weight=1)

        icon_lbl = ctk.CTkLabel(
            row, text=STATUS_ICON[CheckStatus.PENDING],
            font=ctk.CTkFont(size=14),
            text_color=STATUS_COLOR[CheckStatus.PENDING],
            width=28,
        )
        icon_lbl.grid(row=0, column=0, padx=(10, 4), pady=6)

        name_lbl = ctk.CTkLabel(
            row, text=item.name,
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w", width=190,
        )
        name_lbl.grid(row=0, column=1, padx=(0, 8), pady=6, sticky="w")

        detail_lbl = ctk.CTkLabel(
            row, text=item.description,
            font=ctk.CTkFont(size=11),
            text_color="#909090",
            anchor="w",
        )
        detail_lbl.grid(row=0, column=2, padx=4, pady=6, sticky="ew")

        action_btn = ctk.CTkButton(
            row, text="Check", width=88, height=26,
            command=lambda k=item.key: self._on_check_one(k),
        )
        action_btn.grid(row=0, column=3, padx=(6, 10), pady=5)

        self._row_widgets[item.key] = {
            "icon":   icon_lbl,
            "detail": detail_lbl,
            "btn":    action_btn,
        }

    # ── setup section ─────────────────────────────────────────────────────────

    def _build_setup_section(self) -> None:
        outer = ctk.CTkFrame(self, corner_radius=8)
        outer.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 0))
        outer.grid_columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(outer, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        title_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            title_row,
            text="Server Setup",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self._btn_run_setup = ctk.CTkButton(
            title_row, text="▶  Run Setup", width=120, height=28,
            fg_color="#1a4a2a", hover_color="#103520",
            command=self._on_run_setup,
            state="disabled",
        )
        self._btn_run_setup.grid(row=0, column=1, padx=(6, 0))

        # Setup step rows
        steps_frame = ctk.CTkFrame(outer, fg_color="#1a1a1a", corner_radius=6)
        steps_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        runner = SetupRunner(log.log)   # temp instance just to get step names
        for i, name in enumerate(runner.step_names):
            step_row = ctk.CTkFrame(steps_frame, fg_color="transparent", height=30)
            step_row.pack(fill="x", padx=8, pady=2)

            icon_lbl = ctk.CTkLabel(
                step_row,
                text="○",
                font=ctk.CTkFont(size=13),
                text_color="#606060",
                width=24,
            )
            icon_lbl.pack(side="left")

            ctk.CTkLabel(
                step_row,
                text=f"{i + 1}.  {name}",
                font=ctk.CTkFont(size=12),
                text_color="#b0b0b0",
                anchor="w",
            ).pack(side="left", padx=(4, 0))

            self._step_icons.append(icon_lbl)

    # ── log section ───────────────────────────────────────────────────────────

    def _build_log_section(self) -> None:
        outer = ctk.CTkFrame(self, corner_radius=8)
        outer.grid(row=3, column=0, sticky="nsew", padx=12, pady=(8, 0))
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        toolbar = ctk.CTkFrame(outer, fg_color="transparent", height=32)
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))
        toolbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(toolbar, text="Live Log",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            toolbar, text="📋 Copy", width=70, height=24,
            command=self._copy_log,
        ).grid(row=0, column=1, padx=(4, 0))

        ctk.CTkButton(
            toolbar, text="🗑 Clear", width=70, height=24,
            fg_color="#5a3a00", hover_color="#402800",
            command=self._clear_log,
        ).grid(row=0, column=2, padx=(4, 0))

        self._log_box = ctk.CTkTextbox(
            outer,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word",
            state="disabled",
            fg_color="#0d0d0d",
            text_color="#c8c8c8",
        )
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))

    # ── footer ────────────────────────────────────────────────────────────────

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent", height=50)
        footer.grid(row=4, column=0, sticky="ew", padx=12, pady=(6, 10))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            footer,
            text="Complete all required checks and Setup before launching.",
            font=ctk.CTkFont(size=11),
            text_color="#707070",
        ).grid(row=0, column=0, sticky="w")

        self._btn_open_launcher = ctk.CTkButton(
            footer,
            text="Open Launcher  →",
            width=160, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1a4060",
            hover_color="#103050",
            command=self._on_open_launcher,
            state="disabled",
        )
        self._btn_open_launcher.grid(row=0, column=1, padx=(8, 0))

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
    # Row update helpers  (safe to call from any thread via after())
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_row(self, item: PrereqItem) -> None:
        """Marshal row update onto the UI thread."""
        self.after(0, lambda: self._apply_row(item))

    def _apply_row(self, item: PrereqItem) -> None:
        w = self._row_widgets.get(item.key)
        if not w:
            return

        w["icon"].configure(
            text=STATUS_ICON[item.status],
            text_color=STATUS_COLOR[item.status],
        )
        w["detail"].configure(text=item.detail)

        # Determine action button label + state
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
                w["btn"].configure(text="Setup ↓", state="normal",
                                   command=self._scroll_to_setup)
            elif item.key == "wow":
                w["btn"].configure(text="Browse...", state="normal",
                                   command=self._browse_wow_exe)
            elif item.key == "python":
                w["btn"].configure(text="python.org ↗", state="normal",
                                   command=lambda: messagebox.showinfo(
                                       "Python", "Download Python 3.11+ from https://www.python.org/downloads/\nMake sure to check 'Add Python to PATH'."))
            elif item.key == "winget":
                w["btn"].configure(text="Help ↗", state="normal",
                                   command=lambda: messagebox.showinfo(
                                       "winget", "winget ships with Windows 11.\nIf missing, update via the Microsoft Store: 'App Installer'."))
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

        # "Fix All": enabled if any required prereq is MISSING/FAILED and has an auto-installer
        can_fix = any(
            p.status in (CheckStatus.MISSING, CheckStatus.FAILED) and p.can_auto_install
            for p in self._prereqs
        )
        self._btn_fix_all.configure(state="normal" if can_fix else "disabled")

        # "Run Setup": Docker must be running; core prereqs passing
        docker_ok = next((p for p in self._prereqs if p.key == "docker"), None)
        core_ok = docker_ok and docker_ok.status in _PASSING
        self._btn_run_setup.configure(state="normal" if core_ok and not self._busy else "disabled")

        # "Open Launcher": Docker OK + server folder exists
        server_ok = next((p for p in self._prereqs if p.key == "server"), None)
        launcher_ready = (
            core_ok
            and server_ok
            and server_ok.status in _PASSING
        )
        self._btn_open_launcher.configure(
            state="normal" if launcher_ready and not self._busy else "disabled"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Button handlers
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
        icon = STATUS_ICON[status]
        log.log(f"  {icon} {item.name}: {detail}", "INFO")
        self._refresh_row(item)

    def _on_fix_all(self) -> None:
        if self._busy:
            return
        to_fix = [
            p for p in self._prereqs
            if p.status in (CheckStatus.MISSING, CheckStatus.FAILED)
            and p.can_auto_install
        ]
        if not to_fix:
            return
        self._set_busy(True)
        log.log(f"─── Fixing {len(to_fix)} missing prerequisite(s) ───", "INFO")
        threading.Thread(target=lambda: self._fix_worker(to_fix), daemon=True).start()

    def _fix_worker(self, items: list) -> None:
        for item in items:
            self._run_single_install(item)
        log.log("─── Fix pass complete — re-checking all ───", "INFO")
        # Re-check everything after installs
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
                item.status = CheckStatus.WARNING   # will be refined by re-check
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
        # Reset step icons
        for icon_lbl in self._step_icons:
            icon_lbl.configure(text="○", text_color="#606060")
        self._set_busy(True)
        log.log("─── Running server setup ───", "INFO")
        threading.Thread(target=self._setup_worker, daemon=True).start()

    def _setup_worker(self) -> None:
        runner = SetupRunner(log.log)

        def progress(step_idx: int, _total: int, _name: str, success: bool = None) -> None:
            if success is None:
                # step starting
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

    def _on_open_launcher(self) -> None:
        log.log("Opening main launcher...", "INFO")
        self.should_launch = True
        self.destroy()

    # ─────────────────────────────────────────────────────────────────────────
    # Settings helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _browse_wow_exe(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Locate WoW.exe (3.3.5a client)",
            filetypes=[("WoW Executable", "Wow.exe"), ("Executable", "*.exe"), ("All files", "*.*")],
        )
        if chosen:
            cfg = config.load()
            cfg["wow_exe_path"] = chosen
            config.save(cfg)
            log.log(f"WoW.exe set → {chosen}", "INFO")
            wow_item = self._get_item("wow")
            if wow_item:
                self._run_single_check(wow_item)

    def _scroll_to_setup(self) -> None:
        log.log("Scroll down to the Setup section and click 'Run Setup'.", "INFO")

    # ─────────────────────────────────────────────────────────────────────────
    # Log helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _copy_log(self) -> None:
        self._log_box.configure(state="normal")
        content = self._log_box.get("1.0", "end")
        self._log_box.configure(state="disabled")
        self.clipboard_clear()
        self.clipboard_append(content)
        log.log("Log copied to clipboard.", "INFO")

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        log.clear_log_file()
        log.log("Log cleared.", "INFO")

    # ─────────────────────────────────────────────────────────────────────────
    # Cache helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _save_cache(self) -> None:
        """Persist current check results after a full Check All run."""
        results = [
            {"key": p.key, "status": p.status.name, "detail": p.detail}
            for p in self._prereqs
        ]
        config.save_prereq_cache(results)

    def _load_cache(self) -> None:
        """
        Restore last check results from disk.
        If all required items passed, show a banner and enable Open Launcher immediately.
        """
        results, checked_at = config.load_prereq_cache()
        if not results:
            log.log("No previous check results — click 'Check All' to begin.", "INFO")
            return

        # Map cached statuses back onto prereq items
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

        # Refresh all rows with cached data
        for item in self._prereqs:
            self._refresh_row(item)

        # Check if all required items are passing
        all_pass = all(
            p.status in _PASSING
            for p in self._prereqs
            if p.required
        )

        if all_pass:
            banner = f"✅ All checks passed — {checked_at}"
            self._cache_lbl.configure(text=banner, text_color="#1a8c3a")
            self._btn_open_launcher.configure(state="normal")
            log.log(f"Cached results loaded ({checked_at}) — all required checks passed.", "INFO")
            log.log("Click 'Open Launcher' to skip re-checking, or 'Check All' to re-verify.", "INFO")
        else:
            banner = f"⚠️ Last check {checked_at} — some items need attention"
            self._cache_lbl.configure(text=banner, text_color="#c07000")
            log.log(f"Cached results loaded ({checked_at}) — some issues found. Click 'Check All' to re-run.", "INFO")

        self._refresh_global_buttons()

    # ─────────────────────────────────────────────────────────────────────────
    # Misc helpers
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
            self._btn_open_launcher.configure(state="disabled")

    def _get_item(self, key: str) -> Optional[PrereqItem]:
        return next((p for p in self._prereqs if p.key == key), None)

    def on_close(self) -> None:
        if self._busy:
            answer = messagebox.askyesno(
                "Operation in progress",
                "An operation is still running.\nExit anyway?"
            )
            if not answer:
                return
        self.destroy()
