"""The fixed question set: 16 everyday local needs x 3 cities + 2 Hebrew questions = 50.

The wording is what a person types, with one light nudge ("Please name specific
ones") so the engines answer with businesses rather than advice. The nudge is
the same for every engine and is disclosed on the page.
"""

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


CITIES: tuple[tuple[str, str, str], ...] = (
    ("tlv", "Tel Aviv", "IL"),
    ("nyc", "New York City", "US"),
    ("ldn", "London", "UK"),
)

# (code, what the person needs, the situation)
CATEGORIES: tuple[tuple[str, str, str], ...] = (
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

HEBREW: tuple[Query, ...] = (
    Query(
        id="hfa-plumber-he",
        city="Haifa",
        country="IL",
        lang="he",
        category="plumber",
        text="אני צריך שרברב טוב בחיפה לנזילה בצנרת השבוע. על מי אתה ממליץ? תן שמות ספציפיים.",
    ),
    Query(
        id="jlm-dentist-he",
        city="Jerusalem",
        country="IL",
        lang="he",
        category="dentist",
        text="מחפש רופא שיניים טוב בירושלים לבדיקה וסתימה. תמליץ על כמה, בשם.",
    ),
)


def _english(city_code: str, city: str, country: str, cat: str, need: str, why: str) -> Query:
    text = (
        f"I'm looking for {need} in {city} {why}. Who do you recommend? Please name specific ones."
    )
    return Query(
        id=f"{city_code}-{cat}", city=city, country=country, lang="en", category=cat, text=text
    )


QUESTIONS: tuple[Query, ...] = (
    tuple(
        _english(code, city, country, cat, need, why)
        for code, city, country in CITIES
        for cat, need, why in CATEGORIES
    )
    + HEBREW
)

BY_ID: dict[str, Query] = {q.id: q for q in QUESTIONS}
