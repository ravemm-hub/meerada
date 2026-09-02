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
from handover.copilot.pricing import price_for
from handover.copilot.session import Session, SessionManager
from handover.replay.openai_client import ChatCaller

_COCKPIT = Path(__file__).parent / "cockpit.html"

# Current Groq free-tier chat models our grader has verified as working; editable
# in the UI. (Groq rotates model ids — these are the live, measured-good ones.)
FREE_MODELS: list[str] = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

# The desktop / bring-your-keys picker: real ids per provider so the routing is
# obvious (gpt-4o* -> OpenAI, groq/qwen -> Groq, deepseek-chat -> DeepSeek). The
# 'openai/gpt-oss-*' ids are Groq-hosted despite the prefix, so they're not the
# default here — that was a confusing trap for OpenAI users.
DESKTOP_MODELS: list[str] = [
    "gpt-4o-mini",
    "gpt-4o",
    "deepseek-chat",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
]

# Friendly catalog: {id (sent to the API), label (shown), provider (which key it
# needs)}. The picker only offers models whose provider key is connected, so a
# user can never pick a model that 401s on a missing/wrong key.
# (id sent to API, short name, provider = key + grouping, strength tag).
_CATALOG: tuple[tuple[str, str, str, str], ...] = (
    ("claude-3-7-sonnet-latest", "Claude 3.7 Sonnet", "anthropic", "top code"),
    ("claude-3-5-sonnet-latest", "Claude 3.5 Sonnet", "anthropic", "strong"),
    ("claude-3-5-haiku-latest", "Claude 3.5 Haiku", "anthropic", "fast"),
    ("gpt-4o", "GPT-4o", "openai", "strong"),
    ("gpt-4o-mini", "GPT-4o mini", "openai", "fast · cheap"),
    ("anthropic/claude-3.7-sonnet", "Claude 3.7 Sonnet", "openrouter", "top code"),
    ("openai/gpt-4o", "GPT-4o", "openrouter", "strong"),
    ("google/gemini-2.5-pro", "Gemini 2.5 Pro", "openrouter", "strong · vision"),
    ("deepseek/deepseek-r1", "DeepSeek R1", "openrouter", "reasoning"),
    ("deepseek-reasoner", "DeepSeek R1", "deepseek", "reasoning"),
    ("deepseek-chat", "DeepSeek V3", "deepseek", "cheap"),
    ("mistral-large-latest", "Mistral Large", "mistral", "strong"),
    ("openai/gpt-oss-120b", "GPT-OSS 120B", "groq", "free · fast"),
    ("qwen/qwen3.8-27b", "Qwen3", "groq", "free"),
)
MODEL_CATALOG: list[dict[str, str]] = [
    {"id": i, "name": n, "provider": p, "tag": t} for i, n, p, t in _CATALOG
]
PROVIDER_NAMES: dict[str, str] = {
    "anthropic": "Anthropic (Claude)", "openai": "OpenAI", "openrouter": "OpenRouter",
    "deepseek": "DeepSeek", "mistral": "Mistral", "groq": "Groq (free)",
}

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
            price_in, price_out = price_for(model)
            session = Session(
                model,
                self._caller_for(model),
                price_in_per_mtok=price_in,
                price_out_per_mtok=price_out,
                max_tokens=self._max_tokens,
            )
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

    def history(self, sid: str) -> list[dict[str, str]]:
        session = self.sessions.get(sid)
        return [{"role": t.role, "content": t.content} for t in session.history] if session else []


def _caller_for_user(keystore: KeyStore, user: str) -> CallerFor:
    """Build model callers from the signed-in user's own stored provider keys."""
    from handover.copilot.providers import build_caller
    from handover.copilot.router import _provider_of

    def caller(model_id: str) -> ChatCaller:
        provider = _provider_of(model_id)
        key = keystore.get(user, provider)
        if not key:
            raise RuntimeError(f"no key connected for {provider} — add it under Keys")
        return build_caller(provider, key)

    return caller


# A cheap model per provider used only to test that a pasted key actually works.
_VALIDATE_MODEL: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "groq": "openai/gpt-oss-20b",
    "deepseek": "deepseek-chat",
    "mistral": "mistral-small-latest",
    "openrouter": "openai/gpt-4o-mini",
    "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "anthropic": "claude-3-5-haiku-latest",
}


def _validate_key(provider: str, key: str) -> tuple[bool, str]:
    """Make one tiny call so a wrong/mis-pasted key is caught at connect time."""
    from handover.copilot.providers import build_caller

    if not key:
        return False, "empty key"
    try:
        caller = build_caller(provider, key)
        ping = [{"role": "user", "content": "ping"}]
        caller.complete(_VALIDATE_MODEL.get(provider, ""), "", ping, 5)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:100]}"
    return True, ""


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
    # Local vault (desktop app): a single local user brings their OWN provider keys,
    # stored encrypted on this machine, routed per model — no sign-in. Enabled for
    # the desktop launcher / `meerada up --keys`.
    local_vault = os.environ.get("MEERADA_LOCAL_VAULT", "") == "1" and not hosted
    secure = cfg.redirect_uri.startswith("https")
    if dev_login:
        print("WARNING: MEERADA_DEV_LOGIN on — sign-in bypassed. DEV ONLY, never in prod.")

    # Open (no-auth) hosting: when there's no injected caller and no sign-in, build
    # a shared caller from a provider key in the environment (e.g. GROQ_API_KEY),
    # so a deploy can serve real answers to testers with zero sign-up. If no key is
    # present it stays in preview. Auth mode ignores this and uses per-user keys.
    if caller_for is None and not hosted:
        from handover.copilot.providers import caller_for_provider

        provider = os.environ.get("MEERADA_PROVIDER", "groq")
        try:
            caller_for_provider(provider)  # probe: raises if the key is missing
            caller_for = lambda _model_id: caller_for_provider(provider)  # noqa: E731
        except RuntimeError:
            caller_for = None

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
        if hosted or local_vault:  # per-user (or single local) board from the key vault
            if sub not in user_boards:
                user_boards[sub] = Board(_caller_for_user(keystore, sub))
            return user_boards[sub], sub
        return board["board"], sub

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _COCKPIT.read_text(encoding="utf-8")

    @app.get("/models")
    def models(request: Request) -> JSONResponse:
        live = caller_for is not None or hosted or local_vault
        if hosted or local_vault:
            user = current_user(request)
            connected = keystore.providers(str(user["sub"])) if user else []
        else:
            connected = ["groq"] if caller_for is not None else []  # shared tester key
        return JSONResponse(
            {"catalog": MODEL_CATALOG, "connected": connected,
             "provider_names": PROVIDER_NAMES, "live": live}
        )

    @app.get("/me")
    def me(request: Request) -> JSONResponse:
        user = current_user(request)
        if user is None:
            return JSONResponse({"user": None, "auth": True})
        vault = hosted or local_vault
        providers = keystore.providers(str(user["sub"])) if vault else []
        return JSONResponse(
            {
                "user": user.get("email") or user.get("name"),
                "auth": hosted,
                "local_vault": local_vault,
                "providers": providers,
            }
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
        sub = str(user["sub"])
        provider = str(body.get("provider", "")).strip()
        key = str(body.get("key", "")).strip()
        valid, error = _validate_key(provider, key)
        if valid:
            keystore.set(sub, provider, key)
        else:
            keystore.clear(sub, provider)  # drop a stale/wrong key so it self-heals
        return JSONResponse(
            {"ok": valid, "valid": valid, "provider": provider, "error": error,
             "providers": keystore.providers(sub)}
        )

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

    @app.get("/session/history")
    def session_history(request: Request, id: str = "") -> JSONResponse:
        b, _ = board_for(request)
        return JSONResponse({"turns": b.history(id) if b is not None else []})

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
