"""PyInstaller entrypoint for the Meerada LLManager desktop app.

Build (Windows example):
    pip install ".[desktop]" pyinstaller
    pyinstaller --name Meerada --windowed --onefile \
        --collect-all handover --collect-all webview packaging/app_entry.py
The bundled binary lands in dist/. See docs/DESKTOP.md.
"""

from handover.copilot.desktop import run

if __name__ == "__main__":
    run()
