"""Where every jury verdict goes — the training set for our own judge.

The store lives *inside* the tenant (a local SQLite file): the prompt, answer,
context and each juror's reason are kept there in full. What may leave the
tenant is :meth:`export_metadata` only — salted hashes, scores, agreement,
dimension, judge ids — never a character of content (CLAUDE.md tenant rule).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from handover.schema.verdict import JudgeRequest, JuryResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jury_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    dimension TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    answer_hash TEXT NOT NULL,
    request_json TEXT NOT NULL,
    score REAL NOT NULL,
    calibrated_prob REAL NOT NULL,
    agreement REAL NOT NULL,
    kappa REAL,
    low_agreement INTEGER NOT NULL,
    n_judges INTEGER NOT NULL,
    status TEXT NOT NULL,
    cost_usd TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jury_verdicts (
    item_id INTEGER NOT NULL REFERENCES jury_items(item_id),
    judge_id TEXT NOT NULL,
    judge_lab TEXT NOT NULL,
    position TEXT NOT NULL,
    score REAL NOT NULL,
    calibrated_prob REAL NOT NULL,
    verdict_json TEXT NOT NULL
);
"""


class JuryStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def salt(self) -> str:
        row = self._conn.execute("SELECT value FROM meta WHERE key='salt'").fetchone()
        if row is not None:
            return str(row[0])
        salt = secrets.token_hex(32)
        self._conn.execute("INSERT INTO meta VALUES ('salt', ?)", (salt,))
        self._conn.commit()
        return salt

    def _hash(self, text: str) -> str:
        return hashlib.sha256((self.salt() + text).encode("utf-8")).hexdigest()[:32]

    # ---------------------------------------------------------------- write --
    def save(self, req: JudgeRequest, res: JuryResult) -> int:
        cur = self._conn.execute(
            "INSERT INTO jury_items (ts, action, dimension, prompt_hash, answer_hash, "
            "request_json, score, calibrated_prob, agreement, kappa, low_agreement, n_judges, "
            "status, cost_usd) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                datetime.now(tz=UTC).isoformat(),
                req.action,
                req.dimension,
                self._hash(req.prompt),
                self._hash(req.answer),
                req.model_dump_json(),
                res.score,
                res.calibrated_prob,
                res.agreement,
                res.kappa,
                int(res.low_agreement),
                res.n_judges,
                res.verification.status,
                str(res.cost_usd),
            ),
        )
        item_id = int(cur.lastrowid or 0)
        self._conn.executemany(
            "INSERT INTO jury_verdicts VALUES (?,?,?,?,?,?,?)",
            [
                (
                    item_id,
                    v.judge_id,
                    v.judge_lab,
                    v.position,
                    v.score,
                    v.calibrated_prob,
                    v.model_dump_json(),
                )
                for v in res.verdicts
            ],
        )
        self._conn.commit()
        return item_id

    # ----------------------------------------------------------------- read --
    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM jury_items").fetchone()[0])

    def training_rows(self, *, min_agreement: float = 0.6) -> list[dict[str, Any]]:
        """In-tenant only: full content + panel verdict, for training our judge.
        Low-agreement items are excluded — noisy labels teach nothing."""
        rows = self._conn.execute(
            "SELECT item_id, request_json, score, calibrated_prob, agreement, dimension "
            "FROM jury_items WHERE low_agreement=0 AND agreement>=? ORDER BY item_id",
            (min_agreement,),
        ).fetchall()
        out = []
        for item_id, req_json, score, prob, agreement, dim in rows:
            reasons = [
                json.loads(r[0]).get("reason", "")
                for r in self._conn.execute(
                    "SELECT verdict_json FROM jury_verdicts WHERE item_id=?", (item_id,)
                ).fetchall()
            ]
            out.append(
                {
                    "item_id": item_id,
                    "request": json.loads(req_json),
                    "score": score,
                    "calibrated_prob": prob,
                    "agreement": agreement,
                    "dimension": dim,
                    "reasons": reasons,
                }
            )
        return out

    def export_metadata(self) -> list[dict[str, Any]]:
        """What may leave the tenant: hashes and numbers, no content."""
        rows = self._conn.execute(
            "SELECT item_id, ts, action, dimension, prompt_hash, answer_hash, score, "
            "calibrated_prob, agreement, kappa, low_agreement, n_judges, status, cost_usd "
            "FROM jury_items ORDER BY item_id"
        ).fetchall()
        keys = (
            "item_id",
            "ts",
            "action",
            "dimension",
            "prompt_hash",
            "answer_hash",
            "score",
            "calibrated_prob",
            "agreement",
            "kappa",
            "low_agreement",
            "n_judges",
            "status",
            "cost_usd",
        )
        out = []
        for r in rows:
            d = dict(zip(keys, r, strict=True))
            d["low_agreement"] = bool(d["low_agreement"])
            d["judges"] = [
                {"judge_id": j[0], "judge_lab": j[1], "position": j[2], "score": j[3]}
                for j in self._conn.execute(
                    "SELECT judge_id, judge_lab, position, score FROM jury_verdicts "
                    "WHERE item_id=?",
                    (d["item_id"],),
                ).fetchall()
            ]
            out.append(d)
        return out
