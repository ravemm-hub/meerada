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
    endpoint in a threadpool, so sessions genuinely run concurrently.

    The Handshake lives here too: changing a session's model carries the WHOLE
    conversation (history + attached files) to the new model; ``fork`` copies it
    to a second model side by side; ``import_conversation`` seeds a session from
    Claude Code / Claude.ai / ChatGPT history; ``judge`` and ``relay`` compose
    several models into one answer — things no single vendor can offer."""

    def __init__(self, caller_for: CallerFor | None, *, max_tokens: int = 1500) -> None:
        self._caller_for = caller_for
        self._max_tokens = max_tokens
        self.sessions: dict[str, Session] = {}
        self.models: dict[str, str] = {}

    @property
    def live(self) -> bool:
        return self._caller_for is not None

    def _new_session(self, model: str) -> Session:
        assert self._caller_for is not None
        price_in, price_out = price_for(model)
        return Session(
            model, self._caller_for(model), price_in_per_mtok=price_in,
            price_out_per_mtok=price_out, max_tokens=self._max_tokens,
        )

    def open(self, sid: str, model: str) -> Session:
        """Get the session for ``sid`` on ``model``. If it exists on a DIFFERENT
        model, the conversation moves with it — that's the in-place handshake."""
        session = self.sessions.get(sid)
        if session is None:
            session = self._new_session(model)
            self.sessions[sid] = session
        elif session.model_id != model:
            moved = self._new_session(model)
            moved.carry_from(session)
            moved.total_tokens, moved.total_cost = session.total_tokens, session.total_cost
            self.sessions[sid] = session = moved
        self.models[sid] = model
        return session

    def _view(self, sid: str, session: Session) -> dict[str, Any]:
        return {
            "id": sid, "model": session.model_id, "title": session.title,
            "source": session.source, "turns": len(session.history) // 2,
            "attachments": [a["name"] for a in session.attachments],
            "context_chars": sum(len(a["text"]) for a in session.attachments),
            "total_tokens": session.total_tokens, "total_cost": float(session.total_cost),
        }

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
        session = self.open(sid, model)
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

    def describe(self, sid: str) -> dict[str, Any]:
        session = self.sessions.get(sid)
        return self._view(sid, session) if session else {"id": sid, "turns": 0}

    def overview(self) -> list[dict[str, Any]]:
        return [self._view(sid, s) for sid, s in self.sessions.items()]

    # ---- Handshake operations -------------------------------------------
    def import_conversation(
        self, sid: str, model: str, turns: list[dict[str, str]], *, title: str, source: str
    ) -> dict[str, Any]:
        if not self.live:
            return {"error": "connect a key first — imported history needs a live model"}
        session = self._new_session(model)
        session.seed(turns)
        session.title, session.source = title, source
        self.sessions[sid] = session
        self.models[sid] = model
        return self._view(sid, session)

    def fork(self, sid: str, new_sid: str, model: str) -> dict[str, Any]:
        """Copy the whole conversation to a second session on another model, so
        the two continue side by side (the original stays where it is)."""
        src = self.sessions.get(sid)
        if src is None:
            return {"error": "nothing to hand off yet — this session has no history"}
        if not self.live:
            return {"error": "connect a key first"}
        session = self._new_session(model)
        session.carry_from(src)
        self.sessions[new_sid] = session
        self.models[new_sid] = model
        return self._view(new_sid, session)

    def attach(self, sid: str, model: str, files: list[dict[str, str]]) -> dict[str, Any]:
        if not self.live:
            return {"error": "connect a key first"}
        clean = [
            {"name": str(f.get("name", "file"))[:200], "text": str(f.get("text", ""))}
            for f in files if str(f.get("text", "")).strip()
        ]
        session = self.open(sid, model)
        session.attach(clean)
        return self._view(sid, session)

    def judge(self, ids: list[str], judge_sid: str, judge_model: str) -> dict[str, Any]:
        """Cross-model verdict: a judge model reads the latest answer from each
        listed session (same question, different models), ranks them, and writes
        one merged best answer. The verdict lives in its own session so its cost
        is tracked like any other — the ledger stays honest."""
        answers = []
        for sid in ids:
            s = self.sessions.get(sid)
            if s and s.history and s.history[-1].role == "assistant":
                q = s.history[-2].content if len(s.history) >= 2 else ""
                answers.append((sid, s.model_id, q, s.history[-1].content))
        if not answers:
            return {"error": "no answers to judge yet"}
        if not self.live:
            return {"error": "connect a key first"}
        question = answers[0][2]
        body = [
            "You are an impartial judge comparing answers from different AI models "
            "to the same task.",
            f"TASK:\n{question[:6000]}\n",
        ]
        for n, (_, model, _, text) in enumerate(answers, 1):
            body.append(f"--- ANSWER {n} (from {model}) ---\n{text[:8000]}\n")
        body.append(
            "Rank the answers from best to worst with one line of reasoning each "
            "(format: '1. ANSWER n — reason'), then under a heading 'BEST ANSWER' write the "
            "single best final answer, merging correct parts if that improves it. Be concrete."
        )
        session = self.open(judge_sid, judge_model)
        session.title = "⚖️ Verdict"
        session.source = "judge"
        reply = session.ask("\n".join(body))
        return {
            **self._view(judge_sid, session), "text": reply.text, "error": reply.error,
            "judged": [{"id": sid, "model": m} for sid, m, _, _ in answers],
            "input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens,
            "saved_pct": reply.prompt.saved_pct,
        }

    def relay(self, sid: str, model: str, draft_model: str, message: str) -> dict[str, Any]:
        """Draft cheap, polish strong: a cheap model drafts, then the session's
        own (stronger) model refines with the draft in hand. Usually most of the
        quality at a fraction of the strong model's output cost."""
        message = message.strip()
        if not sid or not model or not draft_model or not message:
            return {"error": "session id, model, draft model and message are required"}
        if not self.live:
            return {"error": "connect a key first"}
        session = self.open(sid, model)
        drafter = self._new_session(draft_model)
        drafter.history = list(session.history)
        drafter.attachments = list(session.attachments)
        draft = drafter.ask(message)
        if draft.error:
            err = f"draft ({draft_model}): {draft.error}"
            return {"id": sid, "model": model, "text": "", "error": err}
        polish = (
            f"{message}\n\n[A faster model drafted this answer. Check it, fix mistakes, "
            f"improve it, and reply with the final answer only:]\n{draft.text}"
        )
        reply = session.ask(polish)
        # keep the visible history clean: the user's message, the final answer
        if len(session.history) >= 2 and not reply.error:
            from handover.copilot.session import Turn

            session.history[-2] = Turn(role="user", content=message)
        session.total_tokens += draft.input_tokens + draft.output_tokens
        session.total_cost += draft.cost_usd
        return {
            "id": sid, "model": model, "text": reply.text, "error": reply.error,
            "saved_pct": reply.prompt.saved_pct, "relay": {"draft_model": draft_model,
            "draft_tokens": draft.output_tokens, "draft_cost": float(draft.cost_usd)},
            "input_tokens": reply.input_tokens + draft.input_tokens,
            "output_tokens": reply.output_tokens + draft.output_tokens,
            "turns": len(session.history) // 2,
            "total_tokens": session.total_tokens, "total_cost": float(session.total_cost),
        }


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
    # Reading THIS machine's files (~/.claude scan, attach a folder by path) is
    # only for the desktop app / a localhost `meerada up`. It must be opted in
    # explicitly — an open tester deployment is "not hosted" too, and must never
    # expose its server filesystem.
    local_fs = local_vault or (
        os.environ.get("MEERADA_LOCAL_FS", "") == "1" and not hosted
    )
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
                "local_fs": local_fs,  # desktop/localhost: can scan ~/.claude, attach folders
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
        if b is None:
            return JSONResponse({"turns": []})
        view = b.describe(id)
        view["n_turns"] = view.pop("turns", 0)
        return JSONResponse({**view, "turns": b.history(id)})

    @app.get("/sessions")
    def sessions_list(request: Request) -> JSONResponse:
        b, _ = board_for(request)
        return JSONResponse({"sessions": b.overview() if b is not None else []})

    # ---- the Handshake: import history, move it between models, attach work --
    from handover.copilot import importers as IMP

    import_cache: dict[str, dict[str, list[IMP.Conversation]]] = {}

    def _stash(sub: str, convs: list[IMP.Conversation]) -> str:
        import secrets

        bucket = import_cache.setdefault(sub, {})
        while len(bucket) >= 3:
            bucket.pop(next(iter(bucket)))
        token = secrets.token_urlsafe(8)
        bucket[token] = convs
        return token

    def _import_into(
        b: Board, payload: Mapping[str, Any], conv: IMP.Conversation
    ) -> dict[str, Any]:
        return b.import_conversation(
            str(payload.get("id", "")) or f"imp-{len(b.sessions) + 1}",
            str(payload.get("model", "")), conv.turns, title=conv.title, source=conv.source,
        )

    @app.get("/import/scan")
    def import_scan() -> JSONResponse:
        if not local_fs:
            return JSONResponse({"sessions": [], "local": False})
        return JSONResponse({"sessions": IMP.scan_claude_code(), "local": True})

    @app.post("/import/local")
    async def import_local(request: Request) -> JSONResponse:
        b, _ = board_for(request)
        payload = await request.json()
        path = str(payload.get("path", ""))
        if b is None or not local_fs:
            return JSONResponse({"error": "local import is only available in the desktop app"}, 403)
        if not IMP.is_under_claude_root(path):
            msg = "only Claude Code sessions under ~/.claude can be imported"
            return JSONResponse({"error": msg}, 403)
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return JSONResponse({"error": f"cannot read: {exc}"}, 400)
        conv = IMP.parse_claude_code_jsonl(text, path=path)
        if not conv.turns:
            return JSONResponse({"error": "no conversation turns found in that session"}, 400)
        return JSONResponse(_import_into(b, payload, conv))

    @app.post("/import")
    async def import_upload(request: Request) -> JSONResponse:
        b, sub = board_for(request)
        if b is None or sub is None:
            return JSONResponse({"error": "sign in required"}, status_code=401)
        payload = await request.json()
        text = str(payload.get("text", ""))
        convs = IMP.detect_and_parse(text, str(payload.get("name", "")))
        if not convs:
            return JSONResponse({"error": "couldn't recognise a conversation in that file"}, 400)
        if len(convs) == 1:
            return JSONResponse(_import_into(b, payload, convs[0]))
        token = _stash(sub, convs)
        return JSONResponse(
            {"token": token, "conversations": [c.summary(i) for i, c in enumerate(convs)]}
        )

    @app.post("/import/pick")
    async def import_pick(request: Request) -> JSONResponse:
        b, sub = board_for(request)
        if b is None or sub is None:
            return JSONResponse({"error": "sign in required"}, status_code=401)
        payload = await request.json()
        convs = import_cache.get(sub, {}).get(str(payload.get("token", "")))
        try:
            conv = (convs or [])[int(payload.get("i", -1))]
        except (IndexError, ValueError):
            return JSONResponse({"error": "that import expired — upload the file again"}, 400)
        return JSONResponse(_import_into(b, payload, conv))

    @app.post("/session/fork")
    async def session_fork(request: Request) -> JSONResponse:
        b, _ = board_for(request)
        if b is None:
            return JSONResponse({"error": "sign in required"}, status_code=401)
        p = await request.json()
        return JSONResponse(
            b.fork(str(p.get("id", "")), str(p.get("new_id", "")), str(p.get("model", "")))
        )

    @app.post("/session/attach")
    async def session_attach(request: Request) -> JSONResponse:
        b, _ = board_for(request)
        if b is None:
            return JSONResponse({"error": "sign in required"}, status_code=401)
        p = await request.json()
        files = [f for f in (p.get("files") or []) if isinstance(f, dict)]
        return JSONResponse(b.attach(str(p.get("id", "")), str(p.get("model", "")), files))

    @app.post("/session/attach_path")
    async def session_attach_path(request: Request) -> JSONResponse:
        b, _ = board_for(request)
        p = await request.json()
        if b is None or not local_fs:
            return JSONResponse({"error": "folder attach is desktop-app only"}, 403)
        files, report = IMP.read_folder(str(p.get("path", "")))
        if not files:
            return JSONResponse({"error": "no readable text files there", "report": report}, 400)
        out = b.attach(str(p.get("id", "")), str(p.get("model", "")), files)
        out["report"] = report
        return JSONResponse(out)

    @app.post("/board/judge")
    def board_judge(request: Request, payload: dict[str, Any]) -> JSONResponse:  # sync->threadpool
        b, _ = board_for(request)
        if b is None:
            return JSONResponse({"error": "sign in required"}, status_code=401)
        ids = [str(i) for i in (payload.get("ids") or [])]
        judge_sid, judge_model = str(payload.get("id", "judge")), str(payload.get("model", ""))
        return JSONResponse(b.judge(ids, judge_sid, judge_model))

    @app.post("/session/relay")
    def session_relay(request: Request, payload: dict[str, Any]) -> JSONResponse:  # threadpool
        b, _ = board_for(request)
        if b is None:
            return JSONResponse({"error": "sign in required"}, status_code=401)
        return JSONResponse(
            b.relay(
                str(payload.get("id", "")), str(payload.get("model", "")),
                str(payload.get("draft_model", "")), str(payload.get("message", "")),
            )
        )

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
    import os

    import uvicorn

    from handover.copilot.providers import caller_for_provider

    os.environ.setdefault("MEERADA_LOCAL_FS", "1")  # bound to 127.0.0.1: local files OK

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
