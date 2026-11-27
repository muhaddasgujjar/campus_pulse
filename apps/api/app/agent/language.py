"""Rule-based language detection: no LLM call (D15). 'en' | 'ur' | 'roman_ur'."""

import re
from typing import Literal

Language = Literal["en", "ur", "roman_ur"]

# Arabic-script blocks used for Urdu, as code points so the source stays plain ASCII.
_URDU_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
_URDU_SCRIPT = re.compile("[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in _URDU_RANGES) + "]")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_WORD = re.compile(r"[a-z']+")

# Common Roman Urdu function words. Two or more of them (or one in a short message) is enough.
ROMAN_URDU_MARKERS = frozenset(
    [
        "kya",
        "hai",
        "hain",
        "ho",
        "hoga",
        "hogi",
        "ka",
        "ki",
        "ke",
        "ko",
        "se",
        "mein",
        "mai",  # not "main": it clashes with English ("main campus")
        "mujhe",
        "hum",
        "tum",
        "aap",
        "kab",
        "kahan",
        "kaise",
        "kitni",
        "kitna",
        "kitne",
        "kon",
        "kaun",
        "kis",
        "kyun",
        "nahi",
        "nahin",
        "bhi",
        "aur",
        "ya",
        "batao",
        "bataein",
        "chahiye",
        "karna",
        "karni",
        "karein",
        "kar",
        "raha",
        "rahi",
        "tha",
        "thi",
        "wala",
        "wali",
        "walay",
        "hy",
        "hay",
        "tou",
        "tu",
    ]
)


def detect_language(text: str) -> Language:
    letters = _LETTER.findall(text)
    if letters:
        urdu = sum(1 for ch in letters if _URDU_SCRIPT.match(ch))
        if urdu / len(letters) >= 0.3:
            return "ur"
    words = _WORD.findall(text.lower())
    markers = sum(1 for w in words if w in ROMAN_URDU_MARKERS)
    if markers >= 2 or (markers == 1 and len(words) <= 4):
        return "roman_ur"
    return "en"
