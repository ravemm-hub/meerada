"""Where guard alerts go: console, the desktop (native notification, no extra
dependency), a company webhook (Slack / Teams / Telegram-style JSON POST), and
an in-memory ring the cockpit reads. Sinks are injectable; tests use the ring.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Alert:
    level: str  # info | warn | stalled | burning | blocked
    title: str
    body: str
    session: str = ""
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Sink(Protocol):
    def send(self, alert: Alert) -> None: ...


class RingSink:
    """Keeps the last N alerts for the UI / tests."""

    def __init__(self, size: int = 200) -> None:
        self.items: deque[Alert] = deque(maxlen=size)

    def send(self, alert: Alert) -> None:
        self.items.append(alert)

    def recent(self, n: int = 50) -> list[dict[str, Any]]:
        return [a.as_dict() for a in list(self.items)[-n:]]


class ConsoleSink:
    def __init__(self, write: Callable[[str], None] | None = None) -> None:
        self._write = write or (lambda s: print(s, flush=True))

    def send(self, alert: Alert) -> None:
        icon = {"stalled": "⏸", "burning": "🔥", "blocked": "🔒", "warn": "⚠", "info": "i"}.get(
            alert.level, "•"
        )
        who = f" [{alert.session}]" if alert.session else ""
        self._write(f"{icon} {alert.title}{who} — {alert.body}")


class DesktopSink:
    """Native notification with zero dependencies: PowerShell balloon on Windows,
    osascript on macOS, notify-send on Linux. Failures are swallowed — an alert
    must never crash the guard."""

    def __init__(self, run: Callable[[list[str]], None] | None = None) -> None:
        self._run = run or self._spawn

    @staticmethod
    def _spawn(cmd: list[str]) -> None:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def send(self, alert: Alert) -> None:
        title = f"Meerada Guard: {alert.title}"
        body = alert.body[:220]
        try:
            if sys.platform.startswith("win"):
                ps = (
                    "Add-Type -AssemblyName System.Windows.Forms;"
                    "$n=New-Object System.Windows.Forms.NotifyIcon;"
                    "$n.Icon=[System.Drawing.SystemIcons]::Warning;$n.Visible=$true;"
                    f"$n.ShowBalloonTip(8000,{json.dumps(title)},{json.dumps(body)},'Warning');"
                    "Start-Sleep -Seconds 9;$n.Dispose()"
                )
                self._run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps])
            elif sys.platform == "darwin":
                script = f"display notification {json.dumps(body)} with title {json.dumps(title)}"
                self._run(["osascript", "-e", script])
            else:
                self._run(["notify-send", "-u", "critical", title, body])
        except Exception:
            pass


class WebhookSink:
    """POST every alert as JSON — Slack/Teams incoming webhooks accept ``text``;
    the full alert rides alongside for anything else."""

    def __init__(self, url: str, post: Callable[[str, bytes], None] | None = None) -> None:
        self._url = url
        self._post = post or self._http

    @staticmethod
    def _http(url: str, data: bytes) -> None:
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10):
            pass

    def send(self, alert: Alert) -> None:
        payload = {"text": f"Meerada Guard · {alert.title}: {alert.body}", **alert.as_dict()}
        data = json.dumps(payload).encode()
        threading.Thread(target=self._safe, args=(data,), daemon=True).start()

    def _safe(self, data: bytes) -> None:
        with contextlib.suppress(Exception):
            self._post(self._url, data)


class MultiSink:
    def __init__(self, *sinks: Sink) -> None:
        self._sinks = sinks

    def send(self, alert: Alert) -> None:
        for s in self._sinks:
            with contextlib.suppress(Exception):
                s.send(alert)


def default_sinks(webhook_url: str = "", *, desktop: bool = True) -> tuple[RingSink, MultiSink]:
    ring = RingSink()
    sinks: list[Sink] = [ring, ConsoleSink()]
    if desktop:
        sinks.append(DesktopSink())
    if webhook_url:
        sinks.append(WebhookSink(webhook_url))
    return ring, MultiSink(*sinks)
