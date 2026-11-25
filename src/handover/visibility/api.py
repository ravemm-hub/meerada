"""Live search API — mounted on the hosted app (app.meerada.app):

    GET  /api/search?q=…   what the AI engines show for any question
    GET  /api/audit?url=…  entity audit v0 for a business site

Known lab questions answer from the published state (fetched from meerada.app and
refreshed hourly); anything else runs live on the engines whose keys the server has,
under a hard daily cap and a per-IP allowance, and is cached in memory for a week.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from handover.replay.budget import DailyBudget
from handover.visibility.audit import audit
from handover.visibility.consensus import rank
from handover.visibility.engines import Engine, engines_from_env
from handover.visibility.questions import QUESTIONS
from handover.visibility.questions import Query as LabQuery
from handover.visibility.run import ask_one
from handover.visibility.state import Answer, State

STATE_URL = os.environ.get("MEERADA_STATE_URL", "https://meerada.app/visibility_state.json")
LIVE_ENGINES = os.environ.get(
    "MEERADA_SEARCH_ENGINES", "chatgpt,chatgpt5,claude,gemini,perplexity,grok,mistral"
)
CACHE_TTL = 7 * 24 * 3600
FREE_LIVE_PER_IP = int(os.environ.get("MEERADA_SEARCH_FREE_PER_IP", "3"))
ALLOWED_ORIGINS = ["https://meerada.app", "https://www.meerada.app", "http://localhost:8766"]


def normalize(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())[:200]


class SearchService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: State | None = None
        self._state_at = 0.0
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._ip_live: dict[str, tuple[str, int]] = {}  # ip -> (day, count)
        self.budget = DailyBudget(Decimal(os.environ.get("MEERADA_SEARCH_DAILY_USD", "5")))
        self.engines: list[Engine] = []
        self.skipped: dict[str, str] = {}
        names = [n.strip() for n in LIVE_ENGINES.split(",") if n.strip()]
        self.engines, self.skipped = engines_from_env(names)

    # ---- lab state -------------------------------------------------------------
    def state(self) -> State:
        with self._lock:
            if self._state is None or time.time() - self._state_at > 3600:
                try:
                    with urllib.request.urlopen(STATE_URL, timeout=30) as resp:
                        raw = json.loads(resp.read().decode())
                    self._state = State.model_validate(raw)
                    self._state_at = time.time()
                except Exception:
                    if self._state is None:
                        self._state = State()
            return self._state

    def lab_match(self, q: str) -> LabQuery | None:
        best, best_score = None, 0.0
        for lq in QUESTIONS:
            score = SequenceMatcher(None, q, lq.text.lower()).ratio()
            if score > best_score:
                best, best_score = lq, score
        return best if best is not None and best_score >= 0.86 else None

    def lab_result(self, lq: LabQuery) -> dict[str, Any] | None:
        answers = [a for a in self.state().answers if a.query_id == lq.id and not a.error]
        if not answers:
            return None
        return {
            "source": "lab",
            "query": lq.text,
            "matched": lq.id,
            "city": lq.city,
            "category": lq.category,
            "intent": lq.intent,
            **rank(answers),
        }

    # ---- live -------------------------------------------------------------------
    def _allow_live(self, ip: str) -> bool:
        day = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        d, n = self._ip_live.get(ip, (day, 0))
        if d != day:
            n = 0
        if n >= FREE_LIVE_PER_IP:
            return False
        self._ip_live[ip] = (day, n + 1)
        return True

    def live(self, q: str, ip: str) -> dict[str, Any]:
        if not self.engines:
            return {
                "source": "unavailable",
                "reason": "no engine keys on this server",
                "skipped": self.skipped,
            }
        if not self._allow_live(ip):
            return {
                "source": "unavailable",
                "reason": f"free live searches used for today ({FREE_LIVE_PER_IP}); "
                "known questions are always free",
            }
        est = sum((e.estimate_usd for e in self.engines), Decimal("0"))
        if not self.budget.can_spend(est):
            return {
                "source": "unavailable",
                "reason": "today's measurement budget is spent; try tomorrow",
            }
        now = datetime.now(tz=UTC)
        lq = LabQuery(
            id="live",
            city="",
            country="",
            lang="he" if re.search(r"[֐-׿]", q) else "en",
            category="",
            text=q,
            intent="live",
        )
        with ThreadPoolExecutor(max_workers=len(self.engines)) as pool:
            answers: list[Answer] = list(pool.map(lambda e: ask_one(e, lq, now), self.engines))
        self.budget.record(sum((Decimal(a.cost_usd) for a in answers if not a.error), Decimal("0")))
        ranking = rank(answers)
        return {
            "source": "live",
            "query": q,
            "asked_at": now.isoformat(),
            "errors": {a.engine: a.error[:120] for a in answers if a.error},
            **ranking,
        }

    def search(self, q: str, ip: str) -> dict[str, Any]:
        nq = normalize(q)
        if not nq:
            raise HTTPException(400, "empty query")
        lq = self.lab_match(nq)
        if lq is not None:
            result = self.lab_result(lq)
            if result:
                return result
        hit = self._cache.get(nq)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return {**hit[1], "source": "cache"}
        result = self.live(nq, ip)
        if result.get("source") == "live":
            self._cache[nq] = (time.time(), result)
        return result


def mount_search(app: FastAPI, service: SearchService | None = None) -> SearchService:
    svc = service or SearchService()
    router = APIRouter(prefix="/api")

    @router.get("/search")
    def search(
        request: Request, q: str = Query(..., min_length=2, max_length=200)
    ) -> dict[str, Any]:
        ip = request.headers.get(
            "x-forwarded-for", request.client.host if request.client else "?"
        ).split(",")[0]
        return svc.search(q, ip)

    @router.get("/audit")
    def audit_route(
        url: str = Query(..., min_length=4, max_length=300), name: str = ""
    ) -> dict[str, Any]:
        if not re.match(r"^(https?://)?[\w.-]+\.[a-z]{2,}", url, re.I):
            raise HTTPException(400, "not a site")
        return audit(url, name).as_dict()

    @router.get("/status")
    def status() -> dict[str, Any]:
        return {
            "engines": [e.name for e in svc.engines],
            "skipped": svc.skipped,
            "budget_left_usd": str(svc.budget.remaining()),
            "lab_answers": len(svc.state().answers),
        }

    app.include_router(router)
    app.add_middleware(
        CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET"], allow_headers=["*"]
    )
    return svc
