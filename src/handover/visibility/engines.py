"""The four answer engines, each one HTTP post. ``Post`` is the only network seam;
tests inject a fake. Keys come from the environment (OPENAI_API_KEY,
PERPLEXITY_API_KEY or OPENROUTER_API_KEY, GOOGLE_API_KEY, ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

Post = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class EngineError(RuntimeError):
    """A failed call: HTTP status + the first 300 chars of the body."""


def http_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    """Live poster (not exercised by tests)."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            data: dict[str, Any] = json.loads(resp.read().decode())
            return data
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise EngineError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise EngineError(f"network: {exc.reason}") from exc


@dataclass(frozen=True)
class Reply:
    text: str
    citations: list[str] = field(default_factory=list)
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    searches: int = 0  # web searches the engine actually ran (0 = answered from memory)


class Engine(Protocol):
    name: str
    model: str
    estimate_usd: Decimal

    def ask(self, question: str) -> Reply: ...


def _annotation_urls(message: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for ann in message.get("annotations") or []:
        if not isinstance(ann, dict):
            continue
        # chat completions nest the url under "url_citation"; the Responses API puts it flat
        nested = ann.get("url_citation")
        cite: dict[str, Any] = nested if isinstance(nested, dict) else ann
        url = cite.get("url")
        if url:
            urls.append(str(url))
    return urls


def _usage(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage") or {}
    return int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0)


class ChatGPTSearch:
    """ChatGPT with web search: the Responses API with the ``web_search`` tool on
    ``gpt-4.1-mini`` (the search-preview chat models were retired in 2026). Text
    parts carry url_citation annotations; each ``web_search_call`` item is one
    search. Direct OpenAI key, or OpenRouter."""

    name = "chatgpt"
    estimate_usd = Decimal("0.030")

    def __init__(
        self, api_key: str, post: Post, base_url: str = "https://api.openai.com/v1"
    ) -> None:
        self._key, self._post, self._url = api_key, post, base_url.rstrip("/")
        self.model = "gpt-4.1-mini" if "openai.com" in base_url else "openai/gpt-4.1-mini"

    def ask(self, question: str) -> Reply:
        body: dict[str, Any] = {
            "model": self.model,
            "input": question,
            "tools": [{"type": "web_search", "search_context_size": "low"}],
            "tool_choice": "auto",
        }
        data = self._post(f"{self._url}/responses", {"Authorization": f"Bearer {self._key}"}, body)
        texts: list[str] = []
        citations: list[str] = []
        searches = 0
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "web_search_call":
                searches += 1
            elif item.get("type") == "message":
                for part in item.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "output_text":
                        texts.append(str(part.get("text") or ""))
                        citations += _annotation_urls(part)
        usage = data.get("usage") or {}
        inp = int(usage.get("input_tokens", 0) or 0)
        out = int(usage.get("output_tokens", 0) or 0)
        return Reply("\n".join(texts), citations, self.model, inp, out, searches)


class PerplexitySonar:
    """Perplexity's answer engine (``sonar``). Direct key, or via OpenRouter."""

    name = "perplexity"
    estimate_usd = Decimal("0.008")

    def __init__(
        self, api_key: str, post: Post, base_url: str = "https://api.perplexity.ai"
    ) -> None:
        self._key, self._post, self._url = api_key, post, base_url.rstrip("/")
        self.model = "sonar" if "perplexity.ai" in base_url else "perplexity/sonar"

    def ask(self, question: str) -> Reply:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": question}],
        }
        data = self._post(
            f"{self._url}/chat/completions", {"Authorization": f"Bearer {self._key}"}, body
        )
        message = data["choices"][0]["message"]
        citations = [str(u) for u in data.get("citations") or []] or _annotation_urls(message)
        inp, out = _usage(data)
        return Reply(
            str(message.get("content") or ""), citations, self.model, inp, out, int(bool(citations))
        )


class GeminiGrounded:
    """Gemini with Google Search grounding. Grounding chunks point at a Google
    redirect, so the chunk *title* (the source domain) is kept as the citation."""

    name = "gemini"
    model = "gemini-2.5-flash"
    estimate_usd = Decimal("0.002")

    def __init__(self, api_key: str, post: Post) -> None:
        self._key, self._post = api_key, post

    def ask(self, question: str) -> Reply:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self._key}"
        )
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": question}]}],
            "tools": [{"google_search": {}}],
        }
        data = self._post(url, {}, body)
        candidate = (data.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "\n".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
        citations: list[str] = []
        for chunk in (candidate.get("groundingMetadata") or {}).get("groundingChunks") or []:
            web = chunk.get("web") if isinstance(chunk, dict) else None
            if isinstance(web, dict):
                uri = str(web.get("uri") or "")
                title = str(web.get("title") or "")
                citations.append(title if "vertexaisearch" in uri and title else uri)
        usage = data.get("usageMetadata") or {}
        inp = int(usage.get("promptTokenCount", 0) or 0)
        out = int(usage.get("candidatesTokenCount", 0) or 0)
        return Reply(text, citations, self.model, inp, out, int(bool(citations)))


class ClaudeSearch:
    """Claude with the web_search tool (Messages API)."""

    name = "claude"
    estimate_usd = Decimal("0.020")

    def __init__(self, api_key: str, post: Post, model: str = "") -> None:
        self._key, self._post = api_key, post
        self.model = model or os.environ.get("MEERADA_CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    def ask(self, question: str) -> Reply:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1200,
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            "messages": [{"role": "user", "content": question}],
        }
        headers = {"x-api-key": self._key, "anthropic-version": "2023-06-01"}
        data = self._post("https://api.anthropic.com/v1/messages", headers, body)
        texts: list[str] = []
        citations: list[str] = []
        for block in data.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                texts.append(str(block.get("text") or ""))
                for cite in block.get("citations") or []:
                    if isinstance(cite, dict) and cite.get("url"):
                        citations.append(str(cite["url"]))
            elif block.get("type") == "web_search_tool_result":
                for item in block.get("content") or []:
                    if isinstance(item, dict) and item.get("url"):
                        citations.append(str(item["url"]))
        usage = data.get("usage") or {}
        inp = int(usage.get("input_tokens", 0) or 0)
        out = int(usage.get("output_tokens", 0) or 0)
        searches = int((usage.get("server_tool_use") or {}).get("web_search_requests", 0) or 0)
        return Reply("\n".join(texts), citations, self.model, inp, out, searches)


ALL_ENGINES: tuple[str, ...] = ("chatgpt", "perplexity", "gemini", "claude")
OPENROUTER = "https://openrouter.ai/api/v1"


def engines_from_env(
    names: list[str], env: dict[str, str] | None = None, post: Post = http_post
) -> tuple[list[Engine], dict[str, str]]:
    """Build the requested engines from whatever keys exist; the second value says
    why each missing engine was skipped (never a silent gap on the page)."""
    env = dict(os.environ) if env is None else env
    openrouter = env.get("OPENROUTER_API_KEY", "")
    built: list[Engine] = []
    skipped: dict[str, str] = {}
    for name in names:
        if name == "chatgpt":
            if env.get("OPENAI_API_KEY"):
                built.append(ChatGPTSearch(env["OPENAI_API_KEY"], post))
            elif openrouter:
                built.append(ChatGPTSearch(openrouter, post, OPENROUTER))
            else:
                skipped[name] = "no OPENAI_API_KEY / OPENROUTER_API_KEY"
        elif name == "perplexity":
            if env.get("PERPLEXITY_API_KEY"):
                built.append(PerplexitySonar(env["PERPLEXITY_API_KEY"], post))
            elif openrouter:
                built.append(PerplexitySonar(openrouter, post, OPENROUTER))
            else:
                skipped[name] = "no PERPLEXITY_API_KEY / OPENROUTER_API_KEY"
        elif name == "gemini":
            if env.get("GOOGLE_API_KEY"):
                built.append(GeminiGrounded(env["GOOGLE_API_KEY"], post))
            else:
                skipped[name] = "no GOOGLE_API_KEY"
        elif name == "claude":
            if env.get("ANTHROPIC_API_KEY"):
                built.append(ClaudeSearch(env["ANTHROPIC_API_KEY"], post))
            else:
                skipped[name] = "no ANTHROPIC_API_KEY"
        else:
            skipped[name] = "unknown engine"
    return built, skipped
