"""Lines an answer engine writes that are advice, criteria or table headers, not a business.

``reads_like_advice(text)`` is the shape test the extractor runs after its stoplists:
a Latin phrase of three or more words with at most one capitalised word that carries a
function word or a verb ("Are properly licensed and insured", "Narrow choices by
neighborhood"), a slash/ampersand header in the same lowercase shape ("Pace & duration"),
a two-word criterion ("Office hours", "Schedule fit"), or a Hebrew sentence of four or
more words with a function word ("אם הגורם הוא בניין משותף"). Business names keep their
capitals — "House of Flowers TLV", "Under the Tree", "Baruch The Plumber" all pass.
"""

from __future__ import annotations

import re

_HEB = re.compile(r"[֐-׿]")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

# English words a business name of this shape almost never carries but advice does.
FUNCTION_WORDS = frozenset(
    re.split(
        r"\s+",
        "a an and or of by to for in on at with is are can will should your needs vary matter "
        "exist change offer closer specific where how let say pull narrow recommend help about "
        "any other",
    )
)
# Second word of a two-word criterion: "Office hours", "Wait times", "Schedule fit".
CRITERION_NOUNS = frozenset(
    re.split(
        r"\s+",
        "preferences preference automation certification management focus services service "
        "recommendation hours associations fit times cuts needs appointments options features "
        "quality language outcomes duration formats budget",
    )
)
HEBREW_FUNCTION_WORDS = frozenset(
    re.split(r"\s+", "אם עם של את כדי או הוא היא עבורך לכם שלכם אפשר כדאי מומלץ בקשו לחפש")
)


def _capitalised(words: list[str]) -> int:
    return sum(1 for w in words if w[:1].isupper())


def reads_like_advice(text: str) -> bool:
    plain = text.strip()
    words = plain.split()
    if _HEB.search(plain):
        return len(words) >= 4 and any(w in HEBREW_FUNCTION_WORDS for w in words)
    if len(words) < 2:
        return False
    caps = _capitalised(words)
    if len(words) == 2:
        return caps <= 1 and words[1].islower() and words[1] in CRITERION_NOUNS
    if caps > 1:
        return False
    if any(w.lower() in FUNCTION_WORDS for w in _WORD.findall(plain)):
        return True
    return " / " in plain or " & " in plain
