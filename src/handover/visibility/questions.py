"""The question set of the Search Lab: what people ask an AI when they are about to
choose something — a local tradesperson, a product, a software tool, a hotel, a
B2B supplier, a course, a shop. Three markets (Israel, US, UK) and a few
questions in Hebrew.

The wording is what a person types, with one light nudge per intent ("Please
name specific ones / models / companies") so the engines answer with named
options rather than advice. The nudge is the same for every engine and is
disclosed on the page. Questions are interleaved across intents so every daily
round samples the whole spectrum.
"""

# ruff: noqa: E501  (Hebrew questions and natural-language templates are long literals)
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    id: str
    city: str
    country: str
    lang: str
    category: str
    text: str
    intent: str = "local"


INTENT_LABELS: dict[str, str] = {
    "local": "Local service",
    "product": "Product to buy",
    "software": "Software & tools",
    "travel": "Hotels & travel",
    "b2b": "B2B supplier",
    "education": "Courses & schools",
    "ecommerce": "Online shops",
}

CITIES: tuple[tuple[str, str, str], ...] = (
    ("tlv", "Tel Aviv", "IL"),
    ("nyc", "New York City", "US"),
    ("ldn", "London", "UK"),
)
MARKETS: tuple[tuple[str, str, str], ...] = (
    ("il", "Israel", "IL"),
    ("us", "the US", "US"),
    ("uk", "the UK", "UK"),
)

# ---- local: (code, what the person needs, the situation) -------------------------
LOCAL: tuple[tuple[str, str, str], ...] = (
    ("plumber", "a plumber", "for a leaking pipe this week"),
    ("dentist", "a dentist", "for a check-up and a filling"),
    ("yoga", "a yoga studio", "for a beginner, evening classes"),
    ("italian", "an Italian restaurant", "for a dinner for four"),
    ("trainer", "a personal trainer", "for weight training, twice a week"),
    ("hair", "a hair salon", "for a cut and color"),
    ("lawyer", "a family lawyer", "for a divorce agreement"),
    ("accountant", "an accountant", "for a small business"),
    ("electrician", "an electrician", "to replace a fuse box"),
    ("coffee", "a specialty coffee shop", "to work from with a laptop"),
    ("gym", "a gym", "with a pool, near the center"),
    ("physio", "a physiotherapist", "for a running knee injury"),
    ("florist", "a florist", "for a same-day bouquet delivery"),
    ("photographer", "a wedding photographer", "for a wedding next spring"),
    ("groomer", "a dog groomer", "for a medium-sized dog"),
    ("realtor", "a real estate agent", "to rent a two-bedroom apartment"),
)
# ---- product: (code, item, the situation) — budget written per market -------------
PRODUCT: tuple[tuple[str, str, str], ...] = (
    ("headphones", "noise-cancelling headphones", "for commuting, under {b200}"),
    ("robovac", "a robot vacuum", "for a small apartment with a cat"),
    ("espresso", "an espresso machine for home", "under {b500}"),
    ("stroller", "a stroller", "for a newborn, light enough for stairs"),
    ("runshoes", "running shoes", "for flat feet, 30 km a week"),
    ("monitor", "a 27-inch monitor", "for programming"),
    ("mattress", "a mattress", "for lower-back pain, queen size"),
    ("purifier", "an air purifier", "for a bedroom"),
)
BUDGETS: dict[str, dict[str, str]] = {
    "il": {"b200": "700 shekels", "b500": "2,000 shekels"},
    "us": {"b200": "$200", "b500": "$500"},
    "uk": {"b200": "£150", "b500": "£400"},
}
# ---- software: (code, tool, who) ---------------------------------------------------
SOFTWARE: tuple[tuple[str, str, str], ...] = (
    ("crm", "a CRM", "for a five-person marketing agency"),
    ("invoicing", "an invoicing app", "for a freelancer"),
    ("pm", "a project-management tool", "for a small construction company"),
    ("emailmkt", "an email-marketing tool", "for an online shop with 3,000 subscribers"),
    ("passwords", "a password manager", "for a family of four"),
)
# ---- travel: (code, destination, situation) x traveller profile -------------------
TRAVEL_DEST: tuple[tuple[str, str], ...] = (
    ("lisbon", "Lisbon"),
    ("rome", "Rome"),
    ("tlv", "Tel Aviv"),
    ("nyc", "New York"),
)
TRAVEL_PROFILE: tuple[tuple[str, str], ...] = (
    ("couple", "a boutique hotel for a couple, three nights in May, mid-range"),
    ("family", "a family-friendly hotel with a pool, two kids, one week in August"),
    ("business", "a quiet hotel near the center for a business trip, two nights"),
)
# ---- b2b: (code, supplier, situation) in a city -----------------------------------
B2B: tuple[tuple[str, str, str], ...] = (
    ("webagency", "a web agency", "to build a Shopify store"),
    ("payroll", "a payroll provider", "for a company with 20 employees"),
    ("cpa", "an accounting firm", "for a startup that just raised a seed round"),
    ("recruiter", "a recruiting agency", "to hire two software engineers"),
    ("cleaning", "a commercial cleaning company", "for a 300 m² office"),
)
# ---- education: (code, what, situation) -------------------------------------------
EDUCATION: tuple[tuple[str, str, str], ...] = (
    ("bootcamp", "a bootcamp", "to learn web development, evenings, in {city}"),
    ("driving", "a driving school", "in {city}"),
    ("dataonline", "an online course", "to learn data analysis from zero (I'm in {market})"),
)
# ---- ecommerce: (code, what, situation) -------------------------------------------
ECOMMERCE: tuple[tuple[str, str, str], ...] = (
    ("runninggear", "an online store", "to buy running gear with fast delivery in {market}"),
    ("flowers", "an online flower delivery", "for a birthday in {city}"),
    ("pharmacy", "an online pharmacy", "that delivers in {market}"),
)

HEBREW: tuple[Query, ...] = (
    Query(
        "hfa-plumber-he",
        "Haifa",
        "IL",
        "he",
        "plumber",
        "אני צריך שרברב טוב בחיפה לנזילה בצנרת השבוע. על מי אתה ממליץ? תן שמות ספציפיים.",
        "local",
    ),
    Query(
        "jlm-dentist-he",
        "Jerusalem",
        "IL",
        "he",
        "dentist",
        "מחפש רופא שיניים טוב בירושלים לבדיקה וסתימה. תמליץ על כמה, בשם.",
        "local",
    ),
    Query(
        "il-product-headphones-he",
        "Israel",
        "IL",
        "he",
        "headphones",
        "אני רוצה לקנות אוזניות מבטלות רעשים לנסיעות, עד 700 שקל. אילו דגמים אתה ממליץ? תן שמות ספציפיים.",
        "product",
    ),
    Query(
        "il-software-invoicing-he",
        "Israel",
        "IL",
        "he",
        "invoicing",
        "אני עוסק פטור ומחפש תוכנת חשבוניות פשוטה. על אילו תוכנות אתה ממליץ? תן שמות.",
        "software",
    ),
    Query(
        "il-travel-eilat-family-he",
        "Eilat",
        "IL",
        "he",
        "hotel",
        "מחפש מלון משפחתי באילת עם בריכה לשבוע באוגוסט, שני ילדים. אילו מלונות אתה ממליץ? תן שמות.",
        "travel",
    ),
    Query(
        "il-b2b-webagency-he",
        "Tel Aviv",
        "IL",
        "he",
        "webagency",
        "אנחנו צריכים סוכנות דיגיטל בתל אביב שתבנה לנו חנות שופיפיי. על אילו סוכנויות אתה ממליץ? תן שמות.",
        "b2b",
    ),
)


def _q(qid: str, place: str, country: str, cat: str, text: str, intent: str) -> Query:
    return Query(
        id=qid, city=place, country=country, lang="en", category=cat, text=text, intent=intent
    )


def _local() -> list[Query]:
    return [
        _q(
            f"{code}-{cat}",
            city,
            country,
            cat,
            f"I'm looking for {need} in {city} {why}. Who do you recommend? Please name specific ones.",
            "local",
        )
        for code, city, country in CITIES
        for cat, need, why in LOCAL
    ]


def _product() -> list[Query]:
    return [
        _q(
            f"{m}-product-{cat}",
            market,
            country,
            cat,
            f"I want to buy {item} {why.format(**BUDGETS[m])}. I'm in {market}. "
            "Which ones would you recommend? Please name specific models.",
            "product",
        )
        for m, market, country in MARKETS
        for cat, item, why in PRODUCT
    ]


def _software() -> list[Query]:
    return [
        _q(
            f"{m}-software-{cat}",
            market,
            country,
            cat,
            f"I need {tool} {who}, based in {market}. What would you recommend? "
            "Please name specific products.",
            "software",
        )
        for m, market, country in MARKETS
        for cat, tool, who in SOFTWARE
    ]


def _travel() -> list[Query]:
    country = {"lisbon": "PT", "rome": "IT", "tlv": "IL", "nyc": "US"}
    return [
        _q(
            f"{d}-travel-{p}",
            dest,
            country[d],
            "hotel",
            f"I'm looking for {need} in {dest}. Which hotels would you recommend? "
            "Please name specific ones.",
            "travel",
        )
        for d, dest in TRAVEL_DEST
        for p, need in TRAVEL_PROFILE
    ]


def _b2b() -> list[Query]:
    return [
        _q(
            f"{code}-b2b-{cat}",
            city,
            country,
            cat,
            f"We need {what} in {city} {why}. Which companies would you recommend? "
            "Please name specific ones.",
            "b2b",
        )
        for code, city, country in CITIES
        for cat, what, why in B2B
    ]


def _education() -> list[Query]:
    out: list[Query] = []
    for (code, city, country), (_m, market, _c) in zip(CITIES, MARKETS, strict=True):
        for cat, what, why in EDUCATION:
            why_t = why.format(city=city, market=market)
            out.append(
                _q(
                    f"{code}-education-{cat}",
                    city,
                    country,
                    cat,
                    f"I'm looking for {what} {why_t}. What would you recommend? "
                    "Please name specific ones.",
                    "education",
                )
            )
    return out


def _ecommerce() -> list[Query]:
    out: list[Query] = []
    for (code, city, country), (_m, market, _c) in zip(CITIES, MARKETS, strict=True):
        for cat, what, why in ECOMMERCE:
            why_t = why.format(city=city, market=market)
            out.append(
                _q(
                    f"{code}-ecommerce-{cat}",
                    city,
                    country,
                    cat,
                    f"I'm looking for {what} {why_t}. Which would you recommend? "
                    "Please name specific ones.",
                    "ecommerce",
                )
            )
    return out


def _interleave(groups: list[list[Query]]) -> tuple[Query, ...]:
    """Round-robin across intents so the first rounds already cover every kind of search."""
    out: list[Query] = []
    longest = max(len(g) for g in groups)
    for i in range(longest):
        out.extend(g[i] for g in groups if i < len(g))
    return tuple(out)


QUESTIONS: tuple[Query, ...] = _interleave(
    [_local(), _product(), _software(), _travel(), _b2b(), _education(), _ecommerce(), list(HEBREW)]
)

BY_ID: dict[str, Query] = {q.id: q for q in QUESTIONS}
INTENTS: tuple[str, ...] = tuple(INTENT_LABELS)
