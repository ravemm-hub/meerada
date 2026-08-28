# Making Teeby measurable — the JSON action-envelope

**Goal:** turn Trybe's Teeby from a 0%-grade-A workload into a real Handshake
customer, **without changing what users see.**

## The problem (from Pilot #0)

Teeby replies are warm natural-language text. Meerada can only give a `measured`
grade to a programmatically checkable output. So today: 76% `unknown`, 0
`measured`, empty golden set, no Handshake possible. This is Meerada being
honest — but it means we can't yet prove a migration on Trybe.

## The fix: a hidden structured envelope

Teeby already decides an intent and sometimes an action (reminder, DM, nudge).
Have it emit that decision as a small JSON envelope **alongside** the human
reply — invisible to the user, but schema-checkable by Meerada.

### Envelope schema (this is the contract Meerada verifies)

```json
{
  "type": "object",
  "required": ["reply", "intent"],
  "properties": {
    "reply":      { "type": "string" },
    "intent":     { "type": "string", "enum": ["answer","remind","dm","nudge","navigate","none"] },
    "action":     { "type": ["object","null"] },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
  }
}
```

Every reply that parses against this schema becomes a **grade-A `measured`**
case (signal `json_schema`). `reply` still holds the exact text shown to the
user, so the UX is unchanged — the app renders `reply` and ignores the rest.

## The minimal Trybe change (3 edits, no UX change)

1. **`src/components/TeebyFAB.tsx` — `TEEBY_ANSWER_SYSTEM`:** append
   > Respond ONLY as JSON: `{"reply": "<what the user sees>", "intent": "<one of answer|remind|dm|nudge|navigate|none>", "action": <object or null>, "confidence": <0..1>}`. Put your entire natural answer in `reply`.

2. **The render path (`askClaude` result handling):** parse the JSON, render
   `json.reply`. On parse failure, fall back to showing the raw text (so a bad
   response never breaks the UI). ~5 lines.

3. **`supabase/functions/quick-endpoint`:** already keeps the key server-side;
   no change needed. Optionally log `{intent, confidence, json_valid}` (metadata
   only) to a new `teeby_grades` table so Meerada reads verifiable signal
   directly.

## Then the Handshake runs for real

With envelopes flowing, the Meerada pipeline that already exists does the rest:

```
meerada record  teeby_events.jsonl      # now with json_schema verification
meerada pack                            # golden sets are non-empty (measured cases)
# replay claude-haiku-4-5 -> a cheaper candidate via AnthropicProviderClient
# gap report: per-cluster PASS/BLOCK, the table that sells the product
```

The replay client (`handover.replay.anthropic_client.AnthropicProviderClient`)
is built and tested. The only remaining inputs are a green-light to (a) deploy
the envelope to the live app, and (b) spend a few dollars of API budget on the
candidate replay (protected by the hard DailyBudget cap).

## Why not just do it now

Editing `TEEBY_ANSWER_SYSTEM` changes the behaviour of a **live assistant used
by real Trybe users**. That is an outward-facing production change and a small
real API spend — both are yours to approve, not mine to make unilaterally.
Everything on the Meerada side is ready the moment you say go.
