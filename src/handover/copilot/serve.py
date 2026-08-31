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

from handover.copilot.auth import OAuthConfig
from handover.copilot.keystore import KeyStore
from handover.copilot.optimize import optimize
from handover.copilot.session import Session, SessionManager
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


class Board:
    """Independent named sessions — assign any model to any session and run many
    at once. Unlike a single chat, the user gives DIFFERENT tasks to DIFFERENT
    models (or several sessions on one model) and operates them all in parallel.
    Each session keeps its own history and cost tally; FastAPI runs the sync send
    endpoint in a threadpool, so sessions genuinely run concurrently."""

    def __init__(self, caller_for: CallerFor | None, *, max_tokens: int = 512) -> None:
        self._caller_for = caller_for
        self._max_tokens = max_tokens
        self.sessions: dict[str, Session] = {}
        self.models: dict[str, str] = {}

    def send(self, sid: str, model: str, message: str) -> dict[str, Any]:
        message = message.strip()
        if not sid or not model or not message:
            return {"error": "session id, model and message are required"}
        self.models[sid] = model
        if self._caller_for is None:
            opt = optimize(message, model)
            return {
                "id": sid, "model": model, "text": "",
                "error": "preview only — no API key set",
                "saved_pct": opt.saved_pct, "system": opt.system, "user": opt.user,
                "turns": 0, "total_tokens": 0, "total_cost": 0.0,
            }
        session = self.sessions.get(sid)
        if session is None or session.model_id != model:
            session = Session(model, self._caller_for(model), max_tokens=self._max_tokens)
            self.sessions[sid] = session
        reply = session.ask(message)
        return {
            "id": sid, "model": model, "text": reply.text, "error": reply.error,
            "saved_pct": reply.prompt.saved_pct,
            "input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens,
            "turns": len(session.history) // 2,
            "total_tokens": session.total_tokens, "total_cost": float(session.total_cost),
        }

    def close(self, sid: str) -> None:
        self.sessions.pop(sid, None)
        self.models.pop(sid, None)


def _caller_for_user(keystore: KeyStore, user: str) -> CallerFor:
    """Build model callers from the signed-in user's own stored provider keys."""
    from handover.copilot.router import _provider_of
    from handover.replay.openai_client import ENDPOINTS, HttpChatCaller

    def caller(model_id: str) -> ChatCaller:
        provider = _provider_of(model_id)
        key = keystore.get(user, provider)
        if not key or provider not in ENDPOINTS:
            raise RuntimeError(f"no key connected for {provider} — add it under Keys")
        return HttpChatCaller(ENDPOINTS[provider], key)

    return caller


def build_app(
    caller_for: CallerFor | None = None,
    *,
    cfg: OAuthConfig | None = None,
    keystore: KeyStore | None = None,
) -> FastAPI:
    """Wire the cockpit, the parallel session Board, and (when configured) real
    Google sign-in with per-user key vaults. With no OAuth config the app runs
    open on a single shared caller — exactly the local ``meerada up`` behaviour."""
    import os
    import time

    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

    from handover.copilot import auth as A

    cfg = cfg or A.config_from_env()
    keystore = keystore or KeyStore(
        path=os.environ.get("KEYVAULT_PATH") or None,
        secret=os.environ.get("KEYVAULT_SECRET") or cfg.session_secret,
    )
    google_ok = cfg.configured
    # Auth is enforced whenever a session secret is set. Google is the real path;
    # a dev bypass (explicit opt-in, only when Google is NOT configured) lets you
    # walk the full hosted flow locally. It is never enabled in the deploy config.
    dev_login = os.environ.get("MEERADA_DEV_LOGIN", "") == "1" and not google_ok
    hosted = bool(cfg.session_secret)
    secure = cfg.redirect_uri.startswith("https")
    if dev_login:
        print("WARNING: MEERADA_DEV_LOGIN on — sign-in bypassed. DEV ONLY, never in prod.")

    app = FastAPI(title="Meerada LLManager", docs_url=None, redoc_url=None)
    state: dict[str, SessionManager | None] = {
        "manager": SessionManager(caller_for) if caller_for is not None else None
    }
    board: dict[str, Board] = {"board": Board(caller_for)}
    user_boards: dict[str, Board] = {}

    def current_user(request: Request) -> dict[str, Any] | None:
        if not hosted:
            return {"sub": "local", "email": "local", "name": "local"}
        token = request.cookies.get(A.SESSION_COOKIE, "")
        return A.verify_session(cfg.session_secret, token, now=time.time())

    def board_for(request: Request) -> tuple[Board | None, str | None]:
        user = current_user(request)
        if user is None:
            return None, None
        sub = str(user["sub"])
        if not hosted:
            return board["board"], sub
        if sub not in user_boards:
            user_boards[sub] = Board(_caller_for_user(keystore, sub))
        return user_boards[sub], sub

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _COCKPIT.read_text(encoding="utf-8")

    @app.get("/models")
    def models() -> JSONResponse:
        return JSONResponse({"models": FREE_MODELS, "live": caller_for is not None or hosted})

    @app.get("/me")
    def me(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return JSONResponse({"user": None, "auth": True})
        providers = keystore.providers(str(user["sub"])) if hosted else []
        return JSONResponse(
            {"user": user.get("email") or user.get("name"), "auth": hosted, "providers": providers}
        )

    @app.get("/login")
    def login() -> RedirectResponse:
        if not hosted:
            return RedirectResponse("/")
        if dev_login:  # bypass Google for local end-to-end testing
            token = A.sign_session(
                cfg.session_secret,
                {"sub": "dev", "email": "dev@local", "name": "dev"},
                now=time.time(),
            )
            resp = RedirectResponse("/")
            resp.set_cookie(
                A.SESSION_COOKIE, token, httponly=True, secure=secure,
                samesite="lax", max_age=A.SESSION_TTL_S,
            )
            return resp
        if not google_ok:
            return RedirectResponse("/?auth=unconfigured")
        st = A.new_state(cfg.session_secret)
        resp = RedirectResponse(A.login_url(cfg, st))
        resp.set_cookie(
            A.STATE_COOKIE, st, httponly=True, secure=secure, samesite="lax", max_age=600
        )
        return resp

    @app.get("/auth/callback")
    def auth_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
        saved = request.cookies.get(A.STATE_COOKIE, "")
        if not hosted or not code or state != saved or not A.check_state(cfg.session_secret, state):
            return RedirectResponse("/?auth=failed")
        user = A.exchange_code(cfg, code)
        token = A.sign_session(
            cfg.session_secret, {"sub": user.sub, "email": user.email, "name": user.name},
            now=time.time(),
        )
        resp = RedirectResponse("/")
        resp.set_cookie(
            A.SESSION_COOKIE, token, httponly=True, secure=secure, samesite="lax",
            max_age=A.SESSION_TTL_S,
        )
        resp.delete_cookie(A.STATE_COOKIE)
        return resp

    @app.post("/logout")
    def logout() -> JSONResponse:
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(A.SESSION_COOKIE)
        return resp

    @app.post("/keys")
    async def set_key(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return JSONResponse({"error": "sign in required"}, status_code=401)
        body = await request.json()
        keystore.set(str(user["sub"]), str(body.get("provider", "")), str(body.get("key", "")))
        return JSONResponse({"ok": True, "providers": keystore.providers(str(user["sub"]))})

    @app.post("/optimize")
    async def optimize_endpoint(request: Request) -> JSONResponse:
        return JSONResponse(optimize_view(await request.json()))

    @app.post("/run")
    async def run_endpoint(request: Request) -> JSONResponse:
        return JSONResponse(run_view(await request.json(), caller_for))

    @app.post("/chat")
    async def chat_endpoint(request: Request) -> JSONResponse:
        return JSONResponse(chat_view(state["manager"], await request.json()))

    @app.post("/session/send")
    def session_send(request: Request, payload: dict[str, Any]) -> JSONResponse:  # sync->threadpool
        b, _ = board_for(request)
        if b is None:
            return JSONResponse({"error": "sign in required"}, status_code=401)
        return JSONResponse(
            b.send(
                str(payload.get("id", "")),
                str(payload.get("model", "")),
                str(payload.get("message", "")),
            )
        )

    @app.post("/session/close")
    async def session_close(request: Request) -> JSONResponse:
        b, _ = board_for(request)
        if b is not None:
            b.close(str((await request.json()).get("id", "")))
        return JSONResponse({"ok": True})

    @app.post("/reset")
    def reset_endpoint(request: Request) -> JSONResponse:
        _, sub = board_for(request)
        if not hosted:
            state["manager"] = SessionManager(caller_for) if caller_for is not None else None
            board["board"] = Board(caller_for)
        elif sub is not None:
            user_boards[sub] = Board(_caller_for_user(keystore, sub))
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
