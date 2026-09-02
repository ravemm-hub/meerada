"""Desktop app entrypoint — ``meerada app`` opens the Manager in a native window.

Runs the local FastAPI server on a free port in a background thread and opens a
pywebview window pointing at it, with the local encrypted key vault enabled so
the user brings their own provider keys (stored encrypted under ``~/.meerada``).
Falls back to the default browser if pywebview isn't installed
(``pip install '.[desktop]'``). Everything stays on the machine — keys and
prompts never leave.
"""

import contextlib
import os
import secrets
import socket
import threading
from pathlib import Path


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _ensure_local_vault() -> None:
    """Enable the local encrypted vault, generating a per-machine secret once."""
    home = Path.home() / ".meerada"
    home.mkdir(parents=True, exist_ok=True)
    secret_file = home / "vault.secret"
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        with contextlib.suppress(OSError):  # best-effort: restrict to the owner
            secret_file.chmod(0o600)
    os.environ.setdefault("MEERADA_LOCAL_VAULT", "1")
    os.environ.setdefault("KEYVAULT_PATH", str(home / "keyvault.bin"))
    os.environ.setdefault("KEYVAULT_SECRET", secret_file.read_text(encoding="utf-8").strip())


def _wait_for_server(url: str, timeout: float = 30.0) -> bool:
    """Block until the local server answers, so the window never loads a blank
    page from a not-yet-listening server (the classic race)."""
    import time
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + "/me", timeout=1):
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    return False


def _open_browser_and_block(url: str) -> None:
    import time
    import webbrowser

    print(f"Opening Meerada LLManager in your browser: {url}")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return


def run(port: int | None = None) -> None:
    """Start the local server and open the native window (or the browser)."""
    import uvicorn

    from handover.copilot.serve import build_app

    _ensure_local_vault()
    port = port or _free_port()
    app = build_app()  # reads MEERADA_LOCAL_VAULT + KEYVAULT_* from the environment
    # log_config=None: a --windowed build has no console, so sys.stdout is None and
    # uvicorn's default colour formatter crashes on stdout.isatty(). Skip it.
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    url = f"http://127.0.0.1:{port}"
    _wait_for_server(url)  # never open the window before the server is live

    try:
        import webview  # pywebview
    except ImportError:
        _open_browser_and_block(url)
        return

    try:
        webview.create_window(
            "Meerada LLManager", url, width=1240, height=840, min_size=(900, 600)
        )
        webview.start()
    except Exception as exc:  # no WebView2 / GUI backend -> fall back to the browser
        print(f"native window unavailable ({type(exc).__name__}): {exc} — using the browser")
        _open_browser_and_block(url)
