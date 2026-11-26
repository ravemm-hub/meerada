"""Is this the same business? — name words across Hebrew and English.

A business shows up as "Amnon Electric" in an engine's answer and as "אמנון חשמל" on
Google Maps; "IronCore Fitness Clubs" and "Iron Core" are one gym. ``distinctive`` keeps
the words that say *which* business (not what or where it is, in either language);
``skeleton`` reduces a word to a consonant skeleton that survives transliteration
(אמנון → mn, amnon → mn), so two distinctive words match when their skeletons do.
"""

# ruff: noqa: RUF001

from __future__ import annotations

import re
from difflib import SequenceMatcher

_HEB = re.compile(r"[֐-׿]")

# Words that say what or where a business is, not which one it is.
GENERIC = frozenset(
    re.split(
        r"\s+",
        # English: categories, forms, places
        "the and of in at for dental dentist dentistry clinic clinics yoga studio pilates "
        "salon hair hairdresser barber plumber plumbing plumbers restaurant pizzeria trattoria "
        "cafe coffee gym fitness center centre group office practice ltd inc llc co dr "
        "hotel hotels boutique apartments suites electric electrical electrician law firm "
        "lawyer lawyers attorney attorneys notary cpa accountant accountants accounting "
        "auditors physio physiotherapy physical therapy therapist clubs club flowers flower "
        "florist academy college school institute bootcamp agency digital shop store "
        "beauty cosmetics nails de da do das la le el il "
        "london nyc new york city tel aviv tlv manhattan brooklyn soho israel haifa jerusalem "
        "lisbon lisboa chiado baixa alfama belem bairro alto avenida liberdade rome roma "
        # Hebrew: the same, as Google Business Profiles write them
        "אינסטלטור אינסטלטורים אינסטלציה שרברב שירותי שרותי פתרונות חשמל חשמלאי חשמלאים "
        "מוסמך חירום שעות ביממה מרפאת מרפאה רופא רופאת שיניים לרפואת דר עו עורך עורכי דין משרד "
        "נוטריון גירושין משפחה לענייני רו רואה רואי חשבון חשבונאות סטודיו יוגה פילאטיס כושר "
        "חדר מאמן מאמנת אישי אישית פיזיותרפיה פיזיותרפיסט פיזיו קליניקה קליניקת אוסטאופתיה "
        "פרחי פרחים משלוח חינם מספרה עיצוב שיער קפה בית מסעדה פיצריה איטלקית מלון "
        "תל אביב חיפה הקריות קריות ירושלים ישראל בע מ ושות סניף מרכז בניית אתרים חנויות "
        "שופיפיי אפליקציות דיגיטל שיווק דיגיטלי קורס לימודי בוטקמפ ושירותי",
    )
)
_HEB_PREFIX = "ולבהמכש"  # and / to / in / the / from / as / that, glued to the next word


def is_generic(token: str, ignore: frozenset[str] = GENERIC) -> bool:
    if token in ignore:
        return True
    return bool(_HEB.match(token)) and token[0] in _HEB_PREFIX and token[1:] in ignore


def distinctive(key: str, ignore: frozenset[str] = GENERIC) -> set[str]:
    """The words of a normalised name that identify the business."""
    return {t for t in key.split() if len(t) > 1 and not is_generic(t, ignore)}


def joined(key: str, keep: set[str]) -> str:
    """The distinctive words run together in their order: "Iron Core" → ironcore."""
    return "".join(t for t in key.split() if t in keep)


_HEB_MAP = {
    "א": "", "ע": "", "ה": "", "י": "",
    "ב": "b", "ג": "g", "ד": "d", "ז": "z", "ח": "h", "ט": "t", "כ": "k", "ך": "k",
    "ל": "l", "מ": "m", "ם": "m", "נ": "n", "ן": "n", "ס": "s", "פ": "p", "ף": "p",
    "צ": "c", "ץ": "c", "ק": "k", "ר": "r", "ש": "s", "ת": "t",
}  # fmt: skip
_LATIN_STEPS = (
    ("sch", "s"), ("sh", "s"), ("ch", "h"), ("kh", "h"), ("ph", "p"), ("th", "t"),
    ("tz", "c"), ("ts", "c"), ("ck", "k"), ("x", "ks"), ("q", "k"), ("c", "k"),
    ("f", "p"), ("v", "b"), ("w", "b"), ("j", "g"),
)  # fmt: skip
_VOWELS = re.compile(r"[aeiouy]")
_VAV = "ו"


def skeleton(token: str) -> list[str]:
    """Consonant skeleton(s) of one word; a Hebrew word gives two (vav read as a vowel or
    as v), a Latin word one. Letters map to the same alphabet on both sides."""
    t = token.lower()
    if _HEB.search(t):
        base = "".join(_HEB_MAP.get(ch, ch) for ch in t if ch != _VAV)
        with_v = "".join("b" if ch == _VAV else _HEB_MAP.get(ch, ch) for ch in t)
        return [base, with_v]
    for a, b in _LATIN_STEPS:
        t = t.replace(a, b)
    t = _VOWELS.sub("", t)
    if len(t) > 3:
        t = t.replace("h", "")
    return [t]


def words_match(a: str, b: str) -> bool:
    """Same word: equal, or — across scripts only — consonant skeletons that agree:
    exactly at three letters (amnon/אמנון → mnn), within a letter from four up
    (montefiore/מונטיפיורי). Two words in the same script never match by skeleton;
    "Assaf" is not "Shaffa"."""
    if a == b:
        return True
    if bool(_HEB.search(a)) == bool(_HEB.search(b)):
        return False
    for sa in skeleton(a):
        for sb in skeleton(b):
            if len(sa) < 3 or len(sb) < 3:
                continue
            if sa == sb:
                return True
            if len(sa) >= 4 and len(sb) >= 4 and SequenceMatcher(None, sa, sb).ratio() >= 0.8:
                return True
    return False
