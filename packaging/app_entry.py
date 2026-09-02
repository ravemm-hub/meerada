"""PyInstaller entrypoint for the Meerada LLManager desktop app.

Wraps startup so any crash is written to ~/.meerada/error.log AND shown in a
readable message box (a windowed PyInstaller build otherwise dies silently).

Build (Windows example):
    pip install ".[desktop]" pyinstaller
    pyinstaller --name Meerada --windowed --onedir \
        --collect-all handover --collect-all webview packaging/app_entry.py
See docs/DESKTOP.md.
"""

import traceback
from pathlib import Path


def _report(message: str) -> None:
    try:
        log_dir = Path.home() / ".meerada"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "error.log").write_text(message, encoding="utf-8")
    except Exception:
        pass
    try:  # a visible, copyable dialog on Windows
        import ctypes

        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0, message[-1500:], "Meerada — startup error", 0x10
        )
    except Exception:
        print(message)


def main() -> None:
    try:
        from handover.copilot.desktop import run

        run()
    except Exception:
        _report(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
