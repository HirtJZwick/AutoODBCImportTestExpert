"""
watch_and_test.py
=================
Subagent: watches src/ for Python file changes, then spawns pytest and logs
the result back into Test.md.

Usage:
    python watch_and_test.py

Press Ctrl+C to stop watching.
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR      = PROJECT_ROOT / "src"
TESTS_DIR    = PROJECT_ROOT / "tests"
TEST_MD      = PROJECT_ROOT / "Test.md"

# Explicit venv Python — guarantees pytest and all packages are available
VENV_PYTHON  = PROJECT_ROOT / "zwick_venv_py313_32" / "Scripts" / "python.exe"
PYTHON       = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

# Seconds to wait after the first change before running tests (debounce)
DEBOUNCE_SECONDS = 2.0


# ---------------------------------------------------------------------------
# File-system event handler
# ---------------------------------------------------------------------------

class SourceChangeHandler(FileSystemEventHandler):
    """Trigger the test suite whenever a .py file in src/ is modified."""

    def __init__(self):
        self._last_run: float = 0.0

    def on_modified(self, event):
        self._maybe_run(event.src_path, event.is_directory)

    def on_created(self, event):
        self._maybe_run(event.src_path, event.is_directory)

    def on_moved(self, event):
        # VS Code on Windows saves via rename (temp → final), firing on_moved
        self._maybe_run(event.dest_path, event.is_directory)

    def _maybe_run(self, path: str, is_dir: bool):
        if is_dir:
            return
        if not str(path).endswith(".py"):
            return

        now = time.time()
        if now - self._last_run < DEBOUNCE_SECONDS:
            return  # Skip rapid-fire saves
        self._last_run = now

        rel = Path(path).relative_to(PROJECT_ROOT)
        print(f"\n[Watcher] Change detected: {rel}")
        print("[Watcher] Running tests …\n")
        _run_and_log()


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def _run_and_log():
    """Run pytest and append a one-line result to Test.md."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    result = subprocess.run(
        [PYTHON, "-m", "pytest", str(TESTS_DIR), "-v", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    passed = result.returncode == 0
    status = "Passed" if passed else "Failed"

    # Echo output to terminal
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    print(f"[Watcher] Tests {status} at {timestamp}")

    # Build the log entry
    summary = _extract_summary(result.stdout)
    cause   = _extract_cause(result.stdout) if not passed else ""
    entry   = _format_log_entry(timestamp, status, summary, cause)

    _append_to_test_md(entry)


def _extract_summary(output: str) -> str:
    """Return the pytest short summary line (e.g. '5 passed in 0.42s')."""
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if any(kw in stripped for kw in ("passed", "failed", "error")):
            return stripped
    return "(no summary)"


def _extract_cause(output: str) -> str:
    """Return a comma-separated list of FAILED test names."""
    failed = [l.strip() for l in output.splitlines() if l.startswith("FAILED")]
    return "; ".join(failed) if failed else "see console output"


def _format_log_entry(timestamp: str, status: str, summary: str, cause: str) -> str:
    cause_col = f" — Cause: {cause}" if cause else ""
    return (
        f"| Automated pytest run | {timestamp} | {status}{cause_col} "
        f"| {summary} |"
    )


def _append_to_test_md(entry: str):
    """Append entry after the log-section header in Test.md."""
    content = TEST_MD.read_text(encoding="utf-8")
    TEST_MD.write_text(content.rstrip() + "\n" + entry + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print(f"[Watcher] Using Python: {PYTHON}")
    print(f"[Watcher] Monitoring:   {SRC_DIR.relative_to(PROJECT_ROOT)}")
    print("[Watcher] Running initial test pass …\n")

    # Run once immediately on startup
    _run_and_log()

    observer = Observer()
    observer.schedule(SourceChangeHandler(), str(SRC_DIR), recursive=False)
    observer.start()

    print("\n[Watcher] Watching for file changes. Press Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n[Watcher] Stopped.")

    observer.join()


if __name__ == "__main__":
    main()
