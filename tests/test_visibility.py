"""Visibility Monitor: questions, extraction, engine adapters on recorded bodies,
round-robin + budget, the report's numbers, the page. No live calls."""
# ruff: noqa: E501  (recorded answer texts are long literals)

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from handover.replay.budget import DailyBudget
from handover.visibility import engines as eng
from handover.visibility.extract import extract_mentions, normalize, source_family
from handover.visibility.page import render_page
from handover.visibility.questions import BY_ID, QUESTIONS
from handover.visibility.report import build_report
from handover.visibility.run import ask_one, reextract, tick
from handover.visibility.state import Answer, State, load_state, pick_queries, save_state

NOW = datetime(2026, 11, 24, 7, 0, tzinfo=UTC)

CHATGPT_TEXT = """Here are a few well-regarded plumbers in Tel Aviv:

1. **Shai Plumbing Services** — 24/7 emergency repairs, strong reviews ([site](https://shai-plumb.co.il)).
2. **Instalator Express** - fast response in central Tel Aviv.
3. **Aqua Fix TLV**: specialises in leak detection.

**Tip:** ask for a written quote before work starts.
"""

PERPLEXITY_TEXT = """For a leaking pipe in Tel Aviv, **Shai Plumbing Services** and **Tel Aviv Plumbers Co.** are
frequently recommended[1][2]. **Why it fits**: both offer same-day service.
"""


def test_question_set_is_fifty_unique_and_bilingual() -> None:
    assert len(QUESTIONS) == len({q.id for q in QUESTIONS}) >= 130
    assert sum(q.intent == "local" for q in QUESTIONS) == 50
    assert sum(q.lang == "he" for q in QUESTIONS) == 6
    assert {q.city for q in QUESTIONS} >= {"Tel Aviv", "New York City", "London"}
    assert all(q.text.strip() for q in QUESTIONS)


def test_extraction_reads_lists_bold_links_and_drops_labels() -> None:
    names = [m.name for m in extract_mentions(CHATGPT_TEXT, exclude=("Tel Aviv", "plumber"))]
    assert names == ["Shai Plumbing Services", "Instalator Express", "Aqua Fix TLV"]
    first = extract_mentions(CHATGPT_TEXT)[0]
    assert first.url == "https://shai-plumb.co.il"
    prose = [m.name for m in extract_mentions(PERPLEXITY_TEXT)]
    assert prose == ["Shai Plumbing Services", "Tel Aviv Plumbers Co"]  # trailing dot stripped


def test_extraction_excludes_city_and_category_and_normalizes() -> None:
    text = "- **Tel Aviv** has many options\n- **Plumbers in Tel Aviv** are busy\n- **Mr. Pipe**"
    names = [m.key for m in extract_mentions(text, exclude=("Tel Aviv", "plumber"))]
    assert names == ["mr pipe"]
    assert normalize("  Shai's  Plumbing-Services! ") == "shai s plumbing services"


def test_source_family_classification() -> None:
    assert source_family("https://www.yelp.com/biz/x") == "Yelp"
    assert source_family("https://maps.google.com/?cid=1") == "Google"
    assert source_family("easy.co.il") == "Reviews & directories"
    assert source_family("https://shai-plumb.co.il/about") == "Business sites"
    assert source_family("") == "Unknown"


def _fake_post(bodies: list[dict[str, Any]]) -> tuple[eng.Post, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        calls.append({"url": url, "headers": headers, "body": body})
        return bodies.pop(0)

    return post, calls


def test_chatgpt_adapter_parses_responses_output_and_counts_searches() -> None:
    body = {
        "output": [
            {"type": "web_search_call", "status": "completed"},
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": CHATGPT_TEXT,
                        "annotations": [
                            {"type": "url_citation", "url": "https://yelp.com/biz/shai"}
                        ],
                    }
                ],
            },
        ],
        "usage": {"input_tokens": 40, "output_tokens": 120},
    }
    post, calls = _fake_post([body])
    reply = eng.ChatGPTSearch("k", post).ask("q")
    assert reply.citations == ["https://yelp.com/biz/shai"]
    assert (reply.input_tokens, reply.output_tokens, reply.searches) == (40, 120, 1)
    assert calls[0]["url"].endswith("/responses")
    assert calls[0]["body"]["model"] == "gpt-4.1-mini"
    assert calls[0]["body"]["tools"][0]["type"] == "web_search"


ADVICE_TEXT = """I don't have access to a database of specific dentists in New York City. I'd recommend:

**Here's what I'd recommend instead:**

1. **Ask your primary care doctor** - They can refer you
2. **Check your insurance provider's website** - lists of in-network dentists
3. **Look at review sites** like:
   - Yelp
   - Google Maps/Google Reviews
   - Zocdoc.com (specializes in healthcare provider reviews)
4. **Contact local dental schools** - often offer reduced-cost care
5. **Family Dental NYC** - a real practice, kept as the control

When choosing, consider **Their experience with fillings**, **Availability for new patients**,
**Whether they accept your insurance** and **Confirmation they're still in business**.
"""


CHATGPT_RESPONSES_TEXT = """Here are several reputable plumbers in Tel Aviv:

**[Master Fix Plumbing](https://www.google.com/maps/search/Master+Fix+Plumbing%2C+Tel+Aviv%2C+Israel?utm_source=openai)**
_Tel Aviv, Israel_
Led by Baruch, offering 24/7 services.

**[Eitan Plumber](https://www.google.com/maps/search/Eitan+Plumber%2C+Tel+Aviv%2C+Israel?utm_source=openai)**
_Tel Aviv, Israel_
"""


def test_extraction_reads_bold_links_and_maps_search_citations() -> None:
    cite = (
        "https://www.google.com/maps/search/A.S.+Plumbing%2C+Tel+Aviv%2C+Israel?utm_source=openai"
    )
    found = extract_mentions(
        CHATGPT_RESPONSES_TEXT, exclude=("Tel Aviv", "plumber"), citations=[cite]
    )
    assert [m.name for m in found] == ["Master Fix Plumbing", "Eitan Plumber", "A.S. Plumbing"]
    assert found[0].url is not None and found[0].url.startswith(
        "https://www.google.com/maps/search/Master"
    )
    assert found[2].url == cite


def test_reextract_rereads_stored_answers() -> None:
    state = State()
    state.add(
        Answer(
            engine="chatgpt",
            model="m",
            query_id="tlv-plumber",
            asked_at=NOW,
            text=CHATGPT_RESPONSES_TEXT,
        )
    )
    state.add(
        Answer(
            engine="chatgpt", model="m", query_id="tlv-dentist", asked_at=NOW, text="", error="x"
        )
    )
    assert reextract(state) == 1
    assert state.answers[0].names == ["Master Fix Plumbing", "Eitan Plumber"]


CLAUDE_SPLIT_BOLD = """## סוכנויות מומלצות:

**1.
Boostify
** - בונים פתרונות Shopify מתקדמים

**2.
Webix Digital
** - סוכנות בתל אביב

## Best Options for Your Team Size

**For the best balance of features and affordability** - Pipedrive at £14/seat
**Cost Comparison for 5 Seats** - see below
**Salesflare** - built for agencies
"""


def test_extraction_handles_split_bold_and_header_phrases() -> None:
    names = [m.name for m in extract_mentions(CLAUDE_SPLIT_BOLD, exclude=("Tel Aviv", "webagency"))]
    assert names == ["Boostify", "Webix Digital", "Salesflare"]


def test_extraction_ignores_advice_platforms_and_pronoun_phrases() -> None:
    names = [m.name for m in extract_mentions(ADVICE_TEXT, exclude=("New York City", "dentist"))]
    assert names == ["Family Dental NYC"]


def test_perplexity_direct_and_openrouter_models() -> None:
    body = {
        "choices": [{"message": {"content": PERPLEXITY_TEXT}}],
        "citations": ["https://www.yelp.com/a", "https://easy.co.il/b"],
    }
    post, calls = _fake_post([body, dict(body)])
    assert eng.PerplexitySonar("k", post).ask("q").citations[0].startswith("https://www.yelp")
    assert calls[0]["body"]["model"] == "sonar"
    eng.PerplexitySonar("k", post, eng.OPENROUTER).ask("q")
    assert calls[1]["body"]["model"] == "perplexity/sonar"
    assert calls[1]["url"].startswith(eng.OPENROUTER)


def test_gemini_adapter_keeps_domain_title_for_redirect_chunks() -> None:
    body = {
        "candidates": [
            {
                "content": {"parts": [{"text": "**Aqua Fix TLV** is good."}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {
                            "web": {
                                "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",
                                "title": "yelp.com",
                            }
                        },
                        {"web": {"uri": "https://aquafix.co.il", "title": "Aqua Fix"}},
                    ]
                },
            }
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 30},
    }
    post, calls = _fake_post([body])
    reply = eng.GeminiGrounded("k", post).ask("q")
    assert reply.citations == ["yelp.com", "https://aquafix.co.il"]
    assert "google_search" in str(calls[0]["body"]["tools"])


def test_claude_adapter_collects_text_and_search_result_urls() -> None:
    body = {
        "content": [
            {"type": "web_search_tool_result", "content": [{"url": "https://www.yelp.com/x"}]},
            {
                "type": "text",
                "text": "1. **Shai Plumbing Services**",
                "citations": [
                    {"type": "web_search_result_location", "url": "https://shai-plumb.co.il"}
                ],
            },
        ],
        "usage": {"input_tokens": 5, "output_tokens": 9},
    }
    post, calls = _fake_post([body])
    body["usage"]["server_tool_use"] = {"web_search_requests": 2}
    reply = eng.ClaudeSearch("k", post, model="claude-test").ask("q")
    assert reply.text.startswith("1. **Shai") and reply.searches == 2
    assert reply.citations == ["https://www.yelp.com/x", "https://shai-plumb.co.il"]
    assert calls[0]["headers"]["x-api-key"] == "k"


def test_engines_from_env_falls_back_to_openrouter_and_reports_gaps() -> None:
    post, _ = _fake_post([])
    built, skipped = eng.engines_from_env(
        ["chatgpt", "perplexity", "gemini", "claude", "bogus"], {"OPENROUTER_API_KEY": "or"}, post
    )
    assert [e.name for e in built] == ["chatgpt", "perplexity"]
    assert built[0].model == "openai/gpt-4.1-mini"
    assert set(skipped) == {"gemini", "claude", "bogus"}


class _Stub:
    name = "chatgpt"
    model = "stub"
    estimate_usd = Decimal("0.10")

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.asked: list[str] = []

    def ask(self, question: str) -> eng.Reply:
        self.asked.append(question)
        if self.fail:
            raise eng.EngineError("HTTP 402: billing")
        return eng.Reply(CHATGPT_TEXT, ["https://yelp.com/biz/shai"], "stub", 1, 2, 1)


def test_ask_one_records_error_without_cost() -> None:
    q = BY_ID["tlv-plumber"]
    bad = ask_one(_Stub(fail=True), q, NOW)
    assert bad.error is not None and bad.error.startswith("HTTP 402") and bad.names == []
    good = ask_one(_Stub(), q, NOW)
    assert good.names[:2] == ["Shai Plumbing Services", "Instalator Express"]
    assert good.searches == 1
    assert good.cost_usd == "0.10" and good.citations == ["https://yelp.com/biz/shai"]


def test_pick_queries_is_round_robin_by_age() -> None:
    state = State()
    state.add(Answer(engine="chatgpt", model="m", query_id="tlv-plumber", asked_at=NOW, text=""))
    state.add(
        Answer(
            engine="chatgpt",
            model="m",
            query_id="tlv-dentist",
            asked_at=NOW - timedelta(days=3),
            text="",
            error="x",
        )
    )
    picked = [q.id for q in pick_queries(state, "chatgpt", QUESTIONS, len(QUESTIONS))]
    assert picked[-1] == "tlv-plumber" and picked[-2] == "tlv-dentist"
    assert pick_queries(state, "gemini", QUESTIONS, 2) == list(QUESTIONS[:2])


def test_tick_stops_at_the_budget_and_saves(tmp_path: Path) -> None:
    stub = _Stub()
    state = State()
    budget = DailyBudget(Decimal("0.25"))
    added = tick(state, [stub], budget, per_tick=5, now=NOW, save=tmp_path / "s.json")
    assert len(added) == 2 and budget.spent_today() == Decimal("0.20")
    reloaded = load_state(tmp_path / "s.json")
    assert len(reloaded.answers) == 2 and reloaded.answers[0].names


def test_latest_prefers_a_good_answer_over_a_newer_error() -> None:
    state = State()
    good = Answer(
        engine="chatgpt",
        model="m",
        query_id="q",
        asked_at=NOW,
        text="x",
        names=["A"],
        name_keys=["a"],
    )
    bad = Answer(
        engine="chatgpt",
        model="m",
        query_id="q",
        asked_at=NOW + timedelta(hours=1),
        text="",
        error="boom",
    )
    state.add(good)
    state.add(bad)
    assert state.latest()[("chatgpt", "q")] is good


def _state_two_engines() -> State:
    state = State()
    for qid, names in (("tlv-plumber", ["a", "b"]), ("tlv-dentist", ["c"]), ("ldn-gym", [])):
        state.add(
            Answer(
                engine="chatgpt",
                model="m",
                query_id=qid,
                asked_at=NOW,
                text="t",
                names=[n.upper() for n in names],
                name_keys=names,
                citations=["https://yelp.com/1", "https://x.co.il"],
            )
        )
    state.add(
        Answer(
            engine="gemini",
            model="g",
            query_id="tlv-plumber",
            asked_at=NOW,
            text="t",
            names=["A", "Z"],
            name_keys=["a", "z"],
            citations=["yelp.com"],
        )
    )
    state.add(
        Answer(
            engine="gemini", model="g", query_id="nyc-yoga", asked_at=NOW, text="", error="HTTP 429"
        )
    )
    return state


def test_report_numbers_carry_n_and_ci() -> None:
    report = build_report(_state_two_engines(), QUESTIONS, ["chatgpt", "gemini"], NOW)
    chat = report["engines"][0]
    assert chat["named_rate"]["n"] == 3 and chat["named_rate"]["value"] == pytest.approx(2 / 3)
    assert chat["named_rate"]["ci_low"] is not None
    assert chat["searched_rate"]["n"] == 3 and chat["searched_rate"]["value"] == 0
    assert chat["names_per_answer"] == {"value": 1.5, "n": 2}
    assert chat["sources"][0]["family"] == "Yelp" and chat["sources"][0]["count"] == 3
    gem = report["engines"][1]
    assert gem["errors"] == 1 and gem["last_error"] == "HTTP 429"
    assert report["top_names"][0] == {
        "name": "A",
        "mentions": 2,
        "engines": ["chatgpt", "gemini"],
        "cities": ["Tel Aviv"],
        "categories": ["plumber"],
        "intents": ["local"],
    }
    overlap = report["overlap"][0]
    assert overlap["jaccard"] == {"value": pytest.approx(1 / 3), "n": 1}
    row = next(r for r in report["queries"] if r["id"] == "nyc-yoga")
    assert row["engines"]["gemini"]["error"] == "HTTP 429" and row["engines"]["chatgpt"] is None


def test_page_embeds_the_report_and_escapes_script_close() -> None:
    report = build_report(_state_two_engines(), QUESTIONS, ["chatgpt", "gemini"], NOW)
    report["queries"][0]["text"] = "evil </script><script>alert(1)"
    html = render_page(report)
    assert "</script><script>alert" not in html
    assert '"named_rate"' in html and "How the engines choose" in html
    assert html.count("</script>") == 4  # family.js, analytics, the data block, the renderer


def test_state_round_trip_and_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "e.json"
    empty.write_text("{}", encoding="utf-8")
    assert load_state(empty).answers == []
    state = _state_two_engines()
    save_state(state, tmp_path / "s.json")
    back = load_state(tmp_path / "s.json")
    assert len(back.answers) == 5 and back.answers[0].asked_at == NOW
