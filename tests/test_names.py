"""Business names across Hebrew and English, and the advice lines the extractor drops."""

from __future__ import annotations

from handover.visibility.compare import same_business
from handover.visibility.extract import extract_mentions
from handover.visibility.names import distinctive, skeleton, words_match
from handover.visibility.noise import reads_like_advice


def test_skeleton_survives_transliteration() -> None:
    assert "mnn" in skeleton("אמנון") and skeleton("amnon") == ["mnn"]
    assert words_match("montefiore", "מונטיפיורי")
    assert words_match("gordon", "גורדון")
    assert not words_match("asher", "זיו")
    assert not words_match("miro", "עומר")  # two-letter skeletons prove nothing
    assert not words_match("assaf", "shaffa")  # same script: spelling must agree
    assert not words_match("amoreiras", "lumiares")


def test_distinctive_drops_category_and_city_in_both_languages() -> None:
    assert distinctive("אמנון חשמל") == {"אמנון"}
    assert distinctive("מרפאת מונטיפיורי לפיזיותרפיה ואוסטאופתיה") == {"מונטיפיורי"}
    assert distinctive("ironcore fitness clubs") == {"ironcore"}


def test_same_business_across_scripts_and_spacing() -> None:
    assert same_business("Amnon Electric", "אמנון חשמל")
    assert same_business("Montefiore Clinic", "מרפאת מונטיפיורי לפיזיותרפיה ואוסטאופתיה")
    assert same_business("IronCore Fitness Clubs", "Iron Core")
    assert same_business("Tivoli Oriente Lisboa Hotel", "Hotel Tivoli Oriente")
    assert same_business(
        "Dr. Ben Miller", 'ד"ר בן מילר, רופא שיניים בתל אביב -Tel Aviv Dentist Dr. Ben Miller'
    )
    assert not same_business("NYC Smile Spa", "Smile Lab NYC")
    assert not same_business("262 Boutique Hotel", "LX Boutique Hotel")
    assert not same_business("Asher Electric", "אור וזיו שירותי חשמל")
    assert not same_business("Gordon Gym at Gordon Pool", "פרחי גורדון בן יהודה gordon flowers")
    assert not same_business("Levy Dental Arts", "דר לאה יעקובי")
    assert not same_business("Maor", "מאור - אינסטלטור בתל אביב")  # too short to trust


def test_reads_like_advice_shapes() -> None:
    for line in (
        "Are properly licensed and insured",
        "Can explain the work needed in detail",
        "Narrow choices by neighborhood",
        "Pace & duration",
        "Specialist freelancers / smaller experts",
        "Office hours",
        "Professional associations",
        "Word of mouth",
        "help booking an appointment",
        "אם הגורם הוא בניין משותף",
        "בקשו מהאינסטלטור להגיע עם ציוד לאיתור נזילות",
    ):
        assert reads_like_advice(line), line
    for name in (
        "House of Flowers TLV",
        "Under the Tree",
        "Baruch The Plumber",
        "Yoga with Daniela",
        "Plumber nuni",
        "hum London",
        "monday CRM",
        "iRobot Roomba j9+",
        "Shoshan's - All about Plants, Flowers and Design",
        "Hair & Co / Nathan Jeffrey",
        "יוגה עם חני",
        "צביקה ברגר - אינסטלציה ואיתור נזילות",
    ):
        assert not reads_like_advice(name), name


def test_extractor_drops_advice_lines() -> None:
    text = (
        "- **Asher Electric** — licensed, fast\n"
        "- **Amnon Electric** — fuse boxes\n"
        "Look for electricians who:\n"
        "- **Are properly licensed and insured**\n"
        "- **Can explain the work needed in detail**\n"
        "- **Professional associations**\n"
    )
    assert [m.name for m in extract_mentions(text)] == ["Asher Electric", "Amnon Electric"]
