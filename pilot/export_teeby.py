"""Pilot exporter: Trybe's real Teeby traffic -> Meerada raw events.

Credentials: reads SUPABASE_TOKEN from the environment ONLY — this script
never touches credential files. Run it via the one-liner in pilot/README.

Content NEVER leaves this machine: the JSONL feeds `meerada record` locally,
and a separate content store (input/expected per trace) stays in pilot/ for
the in-tenant Handshake replay.

Honest estimation notes (chat workload without call logs):
- tokens estimated at chars/3 (Hebrew-heavy) + ~3k system prompt, priced at
  haiku-4-5 rates -> every $ figure is DERIVED, not measured.
- wall time approximated by the user->assistant gap, clamped to [1s, 300s].
- verification: JSON-parseable outputs -> measured pass (json_parse);
  otherwise downstream silent acceptance (near-duplicate user message within
  10 minutes = implicit retry -> fail; continued conversation -> pass;
  dead end -> unknown).
"""

import json
import math
import os
import re
import sys
import urllib.request
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

TRYBE = Path(r"C:\Users\rave\Desktop\trybe\trybe-app")
REF = "vytkiwibuohtcmjmslkh"
OUT_DIR = Path(__file__).parent
MODEL_ID = "claude-haiku-4-5-20251001"  # quick-endpoint DEFAULT_MODEL
SYS_EST_TOKENS = 3000
PRICE_IN, PRICE_OUT = 1.0, 5.0  # haiku USD/Mtok


def sql(query: str) -> list[dict]:
    token = os.environ.get("SUPABASE_TOKEN", "").strip()
    if not token:
        sys.exit("SUPABASE_TOKEN env var is required (see pilot/README.md)")
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{REF}/database/query",
        data=json.dumps({"query": query}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "meerada-pilot/0.1",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def teeby_system_prompt() -> str:
    source = (TRYBE / "src" / "components" / "TeebyFAB.tsx").read_text(encoding="utf-8")
    match = re.search(r"TEEBY_ANSWER_SYSTEM = `(.*?)`", source, re.S)
    return match.group(1).strip() if match else "You are Teeby, the Tryber assistant."


def est_tokens(text_len: int) -> int:
    return max(1, math.ceil(text_len / 3))


def jaccard(a: str, b: str) -> float:
    wa, wb = set(a.lower().split()), set(b.lower().split())
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    # Primary pilot source: agent_messages (Teeby/group-agent traffic, grouped
    # per user). teeby_space_messages is folded in as a second session type.
    rows = sql(
        "SELECT id, user_id AS session, role, content, created_at, "
        "$$agent$$ AS kind FROM agent_messages "
        "UNION ALL "
        "SELECT id, space_id AS session, role, content, created_at, "
        "$$space$$ AS kind FROM teeby_space_messages "
        "ORDER BY session, created_at"
    )
    print(f"pulled {len(rows)} teeby/agent messages")
    system_prompt = teeby_system_prompt()
    print(f"system prompt template: {len(system_prompt)} chars")

    spaces: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        spaces[f"{row['kind']}:{row['session']}"].append(row)

    events, store = [], []
    for space_id, msgs in spaces.items():
        for i, msg in enumerate(msgs):
            if msg["role"] != "assistant":
                continue
            context = msgs[max(0, i - 6) : i]
            prev_user = next((m for m in reversed(context) if m["role"] == "user"), None)
            content = msg["content"] or ""

            end_dt = parse_ts(msg["created_at"])
            start_dt = end_dt - timedelta(seconds=8)
            if prev_user:
                candidate = parse_ts(prev_user["created_at"])
                if timedelta(seconds=1) <= end_dt - candidate <= timedelta(seconds=300):
                    start_dt = candidate

            verification = None
            try:
                json.loads(content)
                verification = {
                    "status": "pass", "method": "programmatic", "signal": "json_parse",
                    "confidence": 1.0, "evidence_grade": "measured",
                }
            except ValueError:
                later_users = [m for m in msgs[i + 1 :] if m["role"] == "user"]
                if later_users and prev_user:
                    nxt = later_users[0]
                    retried = (
                        parse_ts(nxt["created_at"]) - end_dt <= timedelta(minutes=10)
                    ) and jaccard(nxt["content"] or "", prev_user["content"] or "") > 0.6
                    verification = {
                        "status": "fail" if retried else "pass",
                        "method": "downstream", "signal": "silent_acceptance",
                        "confidence": 0.7, "evidence_grade": "derived",
                    }

            context_chars = sum(len(m["content"] or "") for m in context)
            in_tokens = SYS_EST_TOKENS + est_tokens(context_chars)
            out_tokens = est_tokens(len(content))
            cost = (in_tokens * PRICE_IN + out_tokens * PRICE_OUT) / 1_000_000

            trace_id = str(uuid.uuid4())
            events.append({
                "provider": "anthropic",
                "model_id": MODEL_ID,
                "trace_id": trace_id,
                "ts_start": start_dt.isoformat(),
                "ts_end": end_dt.isoformat(),
                "messages": [{"role": "system", "content": system_prompt}]
                + [{"role": m["role"], "content": m["content"] or ""} for m in context],
                "output_text": content,
                "tokens": {
                    "input": in_tokens, "input_cached": 0,
                    "output": out_tokens, "reasoning": 0,
                },
                "cost_usd": f"{cost:.6f}",
                "session_id": space_id,
                "verification": verification,
            })
            store.append({
                "trace_id": trace_id,
                "system": system_prompt,
                "user_input": (prev_user or {}).get("content", ""),
                "context": [
                    {"role": m["role"], "content": m["content"] or ""} for m in context
                ],
                "expected_output": content,
            })

    (OUT_DIR / "teeby_events.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8"
    )
    (OUT_DIR / "content_store.jsonl").write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in store), encoding="utf-8"
    )
    graded = sum(1 for e in events if e["verification"])
    measured = sum(
        1
        for e in events
        if e["verification"] and e["verification"]["evidence_grade"] == "measured"
    )
    print(f"exported {len(events)} attempts from {len(spaces)} spaces")
    print(
        f"verification: {graded} graded ({measured} measured), "
        f"{len(events) - graded} unknown"
    )


if __name__ == "__main__":
    main()
