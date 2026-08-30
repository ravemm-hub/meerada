"""Local cockpit server — ``meerada up`` opens the Copilot in the browser.

A thin FastAPI shell over the real engine: ``/optimize`` returns the lean prompt
and its saving (offline, always works); ``/run`` fans the intent out across the
selected models in parallel on the user's own keys. The view functions are pure
and injected, so they are tested with fakes and never call a live API
(CLAUDE.md). The HTTP shell itself (build_app/serve) is a network seam.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from handover.copilot.optimize import optimize
from handover.copilot.session import SessionManager
from handover.replay.openai_client import ChatCaller

_COCKPIT = Path(__file__).parent / "cockpit.html"

# A few current Groq free-tier chat models to seed the picker; editable in the UI.
FREE_MODELS: list[str] = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "gemma2-9b-it",
]

CallerFor = Callable[[str], ChatCaller]


def optimize_view(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Lean prompt + saving per model. Pure and offline — always works."""
    intent = str(payload.get("intent", "")).strip()
    models = [str(m) for m in payload.get("models", [])] or ["claude"]
    results = [
        {
            "model": m,
            "system": o.system,
            "user": o.user,
            "naive_tokens": o.naive_tokens,
            "optimized_tokens": o.optimized_tokens,
            "saved_tokens": o.saved_tokens,
            "saved_pct": o.saved_pct,
        }
        for m in models
        for o in [optimize(intent, m)]
    ]
    return {"intent": intent, "results": results}


def run_view(payload: Mapping[str, Any], caller_for: CallerFor | None) -> dict[str, Any]:
    """Fan the intent out across models in parallel; preview if no caller."""
    intent = str(payload.get("intent", "")).strip()
    models = [str(m) for m in payload.get("models", []) if str(m).strip()]
    if not intent or not models:
        return {"live": False, "error": "intent and at least one model required", "results": []}
    if caller_for is None:
        preview = optimize_view(payload)["results"]
        for row in preview:
            row["text"] = ""
            row["error"] = "preview only — no API key set"
        return {"live": False, "results": preview}
    replies = SessionManager(caller_for).fan_out(intent, models)
    results = [
        {
            "model": r.model_id,
            "text": r.text,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "saved_pct": r.prompt.saved_pct,
            "system": r.prompt.system,
            "user": r.prompt.user,
            "error": r.error,
        }
        for r in replies
    ]
    return {"live": True, "results": results}


def chat_view(manager: SessionManager | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    """One turn of the multi-model cockpit: send a message to every selected
    model in parallel, appending to each model's persistent session. When there
    is no live manager (no key), return the lean-prompt preview instead."""
    message = str(payload.get("message", "")).strip()
    models = [str(m) for m in payload.get("models", []) if str(m).strip()]
    if not message or not models:
        return {"live": manager is not None, "error": "message and models required", "results": []}
    if manager is None:
        preview = optimize_view({"intent": message, "models": models})["results"]
        for row in preview:
            row["text"] = ""
            row["error"] = "preview only — no API key set"
            row["turns"] = 0
        return {"live": False, "results": preview}
    replies = manager.fan_out(message, models)
    results = []
    for reply in replies:
        session = manager.sessions.get(reply.model_id)
        results.append(
            {
                "model": reply.model_id,
                "text": reply.text,
                "error": reply.error,
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
                "saved_pct": reply.prompt.saved_pct,
                "turns": len(session.history) // 2 if session else 1,
                "total_tokens": session.total_tokens if session else 0,
                "total_cost": float(session.total_cost) if session else 0.0,
            }
        )
    return {"live": True, "results": results}


def build_app(caller_for: CallerFor | None = None) -> FastAPI:
    """Wire the cockpit page and endpoints. A persistent SessionManager keeps
    each model's conversation across turns (created lazily, reset on demand)."""
    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="Meerada LLManager", docs_url=None, redoc_url=None)
    state: dict[str, SessionManager | None] = {
        "manager": SessionManager(caller_for) if caller_for is not None else None
    }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _COCKPIT.read_text(encoding="utf-8")

    @app.get("/models")
    def models() -> JSONResponse:
        return JSONResponse({"models": FREE_MODELS, "live": caller_for is not None})

    @app.post("/optimize")
    async def optimize_endpoint(request: Request) -> JSONResponse:
        return JSONResponse(optimize_view(await request.json()))

    @app.post("/run")
    async def run_endpoint(request: Request) -> JSONResponse:
        return JSONResponse(run_view(await request.json(), caller_for))

    @app.post("/chat")
    async def chat_endpoint(request: Request) -> JSONResponse:
        return JSONResponse(chat_view(state["manager"], await request.json()))

    @app.post("/reset")
    def reset_endpoint() -> JSONResponse:
        state["manager"] = SessionManager(caller_for) if caller_for is not None else None
        return JSONResponse({"ok": True})

    return app


def serve(port: int = 8765, provider: str = "groq", *, open_browser: bool = True) -> None:
    """Run the cockpit on localhost. Falls back to preview mode if no key."""
    import uvicorn

    from handover.copilot.providers import caller_for_provider

    caller_for: CallerFor | None
    try:
        caller_for_provider(provider)  # fail fast if no key -> preview mode
        caller_for = lambda _model_id: caller_for_provider(provider)  # noqa: E731
    except RuntimeError:
        caller_for = None

    if open_browser:
        import threading
        import webbrowser

        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run(build_app(caller_for), host="127.0.0.1", port=port, log_level="warning")
