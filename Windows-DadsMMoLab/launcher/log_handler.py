"""
Thread-safe log sink.

Usage:
    from log_handler import log, drain_queue

    log("Server starting...")          # INFO
    log("Docker not found", "ERROR")   # ERROR

    # In UI polling loop (call every 100 ms):
    for entry in drain_queue():
        text_widget.insert("end", entry + "\\n")
"""
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Generator

import config

_queue: queue.Queue = queue.Queue()
_lock = threading.Lock()
_log_path: Path = config.log_file_path()


def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] [{level}] {msg}"
    _queue.put(entry)
    _write_to_file(entry)


def _write_to_file(entry: str) -> None:
    try:
        with _lock:
            with open(_log_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
    except OSError:
        pass  # Never crash the app over a log write


def drain_queue() -> Generator[str, None, None]:
    """Yield all pending log entries without blocking. Safe to call from UI thread."""
    while True:
        try:
            yield _queue.get_nowait()
        except queue.Empty:
            break


def read_log_file() -> str:
    """Return the full contents of the persistent log file."""
    try:
        return _log_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def clear_log_file() -> None:
    try:
        _log_path.write_text("", encoding="utf-8")
    except OSError:
        pass
