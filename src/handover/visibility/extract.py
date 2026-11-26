"""Pull the businesses an answer names, by program (evidence ``derived``).

Answer engines write lists: numbered or bulleted items whose name is bold, a
markdown link, or the text before the first dash/colon. Bold spans in prose are
taken too (Perplexity's style). Labels like "Tip:" or "Why it fits" are dropped
by a short stoplist and by shape. No model is asked to read the answer — a
program's reading is reproducible and free.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import unquote_plus, urlparse

from handover.visibility.noise import reads_like_advice

_ITEM = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+(.*\S)\s*$")
_HEADER = re.compile(r"^\s*#{2,4}\s+(.*\S)\s*$")
_BOLD = re.compile(r"\*\*([^*]{1,300}?)\*\*")  # may span a line break (Claude's lists)
_LEADING_NUMBER = re.compile(r"^\s*\d{1,2}[.)]\s*")
_DOMAIN = re.compile(
    r"^\[?[\w.-]+\.(?:com|co|net|org|il|uk|io|ai|de|fr|es|it|pt)(?:\.[a-z]{2})?\]?$", re.I
)
_WS = re.compile(r"\s+")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_URL = re.compile(r"https?://[^\s)\]]+")
_SPLIT = re.compile(r"\s+[\u2014\u2013-]\s+|:\s|\s\(|,\s|\s\|\s")  # dash, en/em dash, colon
_CLEAN = re.compile(r"[\W_]+", re.UNICODE)
_MAPS = re.compile(r"google\.[a-z.]+/maps/search/([^?]+)")

_STOP = {
    "tip",
    "tips",
    "note",
    "notes",
    "summary",
    "overview",
    "pros",
    "cons",
    "why",
    "why it fits",
    "what to expect",
    "price",
    "prices",
    "pricing",
    "rating",
    "ratings",
    "address",
    "hours",
    "location",
    "website",
    "phone",
    "bottom line",
    "my pick",
    "best overall",
    "best value",
    "how to choose",
    "how to book",
    "recommendation",
    "recommendations",
    "disclaimer",
    "sources",
    "important",
    "keep in mind",
    "next steps",
    "final thoughts",
    "in short",
    "verdict",
    "a few tips",
    "quick tips",
    "one more thing",
    "caveat",
    "caveats",
}
_STOP_PREFIX = ("how ", "what ", "why ", "when ", "where ", "if ", "tip", "note", "before ")
# Advice, not a business: "Ask your primary care doctor", "Check your insurance provider's website"
_ADVICE_PREFIX = (
    "describe ",
    "tell ",
    "mention ",
    "have ",
    "keep ",
    "turn ",
    "shut ",
    "take ",
    "bring ",
    "prepare ",
    "expect ",
    "quick ",
    "top/local",
    "for ",
    "cost ",
    "budget ",
    "overall ",
    "strong ",
    "other ",
    "honorable ",
    "runner",
    "also ",
    "alternatively",
    "bonus",
    "ask ",
    "check ",
    "look ",
    "call ",
    "contact ",
    "use ",
    "search ",
    "try ",
    "visit ",
    "read ",
    "compare ",
    "verify ",
    "confirm ",
    "consider ",
    "make sure",
    "whether ",
    "their ",
    "your ",
    "current ",
    "real ",
    "local ",
    "get ",
    "avoid ",
    "always ",
    "never ",
    "book ",
    "request ",
    "go ",
    "find ",
    "browse ",
    "start ",
    "join ",
    "post ",
    "see ",
    "choose ",
    "pick ",
    "ensure ",
)
_PRONOUN = re.compile(r"\b(i|they|you|your|their|we|our|them)\b")
# Words a business name almost never carries but advice lines do
_GENERIC_WORDS = {
    "comparison",
    "summary",
    "options",
    "specifically",
    # Hebrew header words: recommended / options / summary / recommendations / tips / note
    "מומלצות",
    "מומלצים",
    "אפשרויות",
    "סיכום",
    "המלצות",
    "טיפים",
    "הערה",
    "השוואה",
    "reviews",
    "ratings",
    "directories",
    "directory",
    "recommendations",
    "information",
    "policy",
    "insurance",
    "availability",
    "pricing",
    "experience",
    "website",
    "websites",
    "groups",
    "listings",
    "platforms",
    "apps",
    "sites",
    "search",
    "numbers",
    "confirmation",
    "quote",
    "quotes",
    "estimate",
    "estimates",
    "credentials",
    "references",
}
# The engines' own sources and the big platforms are not businesses to recommend
_PLATFORMS = {
    "google",
    "google maps",
    "google maps search",
    "google maps google reviews",
    "google reviews",
    "google search",
    "yelp",
    "zocdoc",
    "zocdoc com",
    "healthgrades",
    "healthgrades com",
    "waze",
    "facebook",
    "instagram",
    "tiktok",
    "reddit",
    "tripadvisor",
    "bing",
    "apple maps",
    "yellow pages",
    "yellow pages israel",
    "easy",
    "midrag",
    "b144",
    "nextdoor",
    "thumbtack",
    "angi",
    "checkatrade",
    "trustpilot",
    "linkedin",
    "youtube",
    "whatsapp",
    "opentable",
    "classpass",
    "mindbody",
    "treatwell",
    "booksy",
    "fresha",
    "bark",
    "rated people",
    "mybuilder",
    "timeout",
    "time out",
    "the infatuation",
    "eater",
    "wolt",
    "10bis",
}


@dataclass(frozen=True)
class Mention:
    name: str
    key: str
    url: str | None


def normalize(name: str) -> str:
    return _CLEAN.sub(" ", name).strip().lower()


def _looks_like_name(name: str) -> bool:
    plain = name.strip().strip("*_\"'\u201c\u201d\u2018\u2019").rstrip(":.!?")
    low = plain.lower()
    if not (2 <= len(plain) <= 60) or low in _STOP or low.startswith(_STOP_PREFIX):
        return False
    words = plain.split()
    if len(words) > 8 or plain.endswith(":"):
        return False
    if low.startswith(_ADVICE_PREFIX) or _PRONOUN.search(low) or _DOMAIN.match(plain):
        return False
    key = normalize(plain)
    if key in _PLATFORMS or any(w in _GENERIC_WORDS for w in key.split()):
        return False
    if reads_like_advice(plain):
        return False
    letters = sum(ch.isalpha() for ch in plain)
    return letters >= 2


def _name_of(item: str) -> str | None:
    bold = _BOLD.search(item)
    if bold:
        return bold.group(1).strip()
    head = _SPLIT.split(item, maxsplit=1)[0].strip()
    link = _LINK.search(item)
    # "- Name — note ([easy.co.il](url))": the link is the citation, the name is the head.
    if link and (link.start() == 0 or not head or _DOMAIN.search(head)):
        return link.group(1).strip()
    return head or None


def _url_of(item: str) -> str | None:
    link = _LINK.search(item)
    if link:
        return link.group(2)
    raw = _URL.search(item)
    return raw.group(0).rstrip(".,") if raw else None


def _add(found: dict[str, Mention], name: str | None, url: str | None) -> None:
    if not name:
        return
    name = _LEADING_NUMBER.sub("", _WS.sub(" ", name)).strip()
    link = _LINK.search(name)
    if link:  # **[Name](url)** — ChatGPT's format: the name is the link text
        name, url = link.group(1), url or link.group(2)
    if not _looks_like_name(name):
        return
    clean = name.strip().strip("*_\"'\u201c\u201d\u2018\u2019").rstrip(":.!?")
    key = normalize(clean)
    if key and key not in found:
        found[key] = Mention(name=clean, key=key, url=url)


def _maps_search_name(url: str) -> str | None:
    """ChatGPT cites a business as a Google Maps search: .../maps/search/Name%2C+City."""
    match = _MAPS.search(url)
    if not match:
        return None
    return unquote_plus(match.group(1)).split(",")[0].strip() or None


def extract_mentions(
    text: str, exclude: tuple[str, ...] = (), citations: Sequence[str] = ()
) -> list[Mention]:
    """Businesses named in one answer, in order of appearance, deduplicated by key.
    ``exclude`` lists words that are never a business (the city, the category);
    ``citations`` adds names carried by Google-Maps-search links."""
    found: dict[str, Mention] = {}
    for line in text.splitlines():
        item = _ITEM.match(line)
        header = _HEADER.match(line)
        if item:
            _add(found, _name_of(item.group(1)), _url_of(item.group(1)))
        elif header:
            _add(found, _name_of(header.group(1)), _url_of(header.group(1)))
    for bold in _BOLD.finditer(text):
        _add(found, bold.group(1), None)
    for cite in citations:
        _add(found, _maps_search_name(cite), cite)
    banned = {normalize(word) for word in exclude}
    return [m for m in found.values() if m.key not in banned and not _is_generic(m.key, banned)]


def _is_generic(key: str, banned: set[str]) -> bool:
    """The category or the city on its own ("Plumbers in Tel Aviv", "Tel Aviv") is not a
    business; "Eitan Plumber" or "Oca London" is, so only whole-phrase forms are dropped."""
    for b in banned:
        if not b:
            continue
        if key in (b, b + "s") or key.endswith(" in " + b) or key.startswith(b + " in "):
            return True
        if key.endswith(" in " + b + " area"):
            return True
    return False


# Where the citations point: the source families the engines lean on.
_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Yelp", ("yelp.",)),
    ("Tripadvisor", ("tripadvisor.",)),
    ("Google", ("google.", "goo.gl", "g.page")),
    ("Reddit", ("reddit.",)),
    ("Social", ("facebook.", "instagram.", "tiktok.", "linkedin.", "x.com", "twitter.")),
    (
        "Reviews & directories",
        (
            "trustpilot.",
            "checkatrade.",
            "yell.",
            "thumbtack.",
            "angi.",
            "zocdoc.",
            "healthgrades.",
            "treatwell.",
            "classpass.",
            "mindbody.",
            "timeout.",
            "theinfatuation.",
            "opentable.",
            "easy.co.il",
            "zap.co.il",
            "rest.co.il",
            "midrag.",
            "d.co.il",
            "b144.",
            "doctors.co.il",
            "wolt.",
            "booksy.",
            "fresha.",
            "bark.com",
            "ratedpeople.",
            "mybuilder.",
            "houzz.",
        ),
    ),
    ("Wikipedia", ("wikipedia.",)),
    (
        "News & magazines",
        (
            "nytimes.",
            "theguardian.",
            "standard.co.uk",
            "timeout.",
            "eater.",
            "ynet.",
            "haaretz.",
            "mako.",
            "walla.",
            "secrettel",
            "secretldn",
            "secretnyc",
            "forbes.",
            "cntraveler.",
        ),
    ),
)


def source_family(citation: str) -> str:
    host = urlparse(citation if "://" in citation else f"https://{citation}").netloc.lower()
    host = host.removeprefix("www.")
    if not host:
        return "Unknown"
    for family, needles in _FAMILIES:
        if any(n in host for n in needles):
            return family
    return "Business sites"
