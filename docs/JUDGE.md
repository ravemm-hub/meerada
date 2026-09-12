# The Judge layer — Cross-check today, our own judge tomorrow

**One line:** Meerada is the model that examines models. Today that is a
**jury** of three models from three different labs examining every answer
(SPEC §5.2); tomorrow it is a small judge of our own, trained on the verdicts
the jury leaves behind. Decision of 2026-09-12; phases T20–T24 in `TASKS.md`.

## What a user gets now

### 🔎 Cross-check (LLManager button · `meerada crosscheck`)
1. Send one task to several models (Send to all / Compare all).
2. Press **Cross-check**. For every answer, a panel of three jurors is seated
   from the *other* labs you have keys for — never the answer's own family.
3. Each juror returns a frozen verdict: score 0–1, its own confidence, flagged
   spans, one line of reason. The panel combines them: mean score, agreement,
   pass / fail / unknown.
4. The report lands in its own session (its cost on the ledger): ranked
   answers, jurors' words, flagged claims, a winner — or "no winner" when no
   panel agreed. A score chip appears on each examined session.

Dimension is picked from the task: `faithfulness` when the session has
attached context, `code_correctness` when the answer is code, else
`instruction_following`.

```
meerada crosscheck "Summarize this memo in 3 bullets" --models gpt-4o-mini,claude-haiku-4-5-20251001,gemini-2.5-flash \
    --context memo.txt --budget 1 --store ~/.meerada/jury.sqlite
```

## The rules the jury cannot break (all tested)
- three jurors from three labs, or the result is `unknown`;
- a juror never judges its own family (`answer_family`);
- pairwise comparisons run twice in reversed order — position bias cancels;
- the rubric deducts explicitly for padding — length bias cancels;
- Fleiss' kappa across a batch is always reported; kappa < 0.4 or a split
  panel → `low_agreement` → `unknown`, never a public number;
- a hard daily budget (`MEERADA_JURY_DAILY_USD`, default $2 in the app);
- verdicts are `derived` evidence: a programmatic check always outranks them.

## What the jury leaves behind
Every verdict is written to `~/.meerada/jury.sqlite` on the user's machine
(never on the hosted tester). Content stays there; `export_metadata()` yields
hashes and numbers only. `training_rows()` (agreement ≥ 0.6) is the training
set for T23 — the model that replaces the jury and runs inside the tenant.

## Code map
| Piece | File |
|---|---|
| Verdict schema (frozen) | `src/handover/schema/verdict.py` |
| Rubrics + JSON contract + parser | `src/handover/verify/rubrics.py` |
| The jury | `src/handover/verify/jury.py` |
| Verdict store | `src/handover/verify/jury_store.py` |
| Cross-check orchestration (labs, panels, report) | `src/handover/copilot/crosscheck.py` |
| Board + `/board/crosscheck` + cockpit button | `src/handover/copilot/serve.py`, `cockpit.html` |
| CLI | `src/handover/cli/crosscheck_cmd.py` |

## Next (T22 → T24)
- `bench/hallucinate.py`: controlled hallucination injection on the battery →
  labelled data with known truth; a frozen eval set per dimension.
- Hallucination column on the exchange from `faithfulness` verdicts.
- Train Qwen 3 8B / 1.7B as the judge (SFT → RL with verified reward + Brier
  penalty); compare against the jury, GPT-4o-as-judge, Lynx, Selene. First GPU
  spend, $3–8K — an explicit decision stop.
- The judge replaces the jury in-tenant and retrains monthly on new models'
  failure modes; the reliability ledger becomes a product.
