"""Redaction of personal identifiers (SEC-3, SEC-5, Memory rule 6).

Rule-based (no LLM, D15). Applied to logs now. In M2 and M3 it is also applied to
user text before it is stored or sent to the LLM. Order matters: roll numbers and
CNICs are matched before phone numbers so a CNIC is never half-replaced as a phone.
"""

import re

ROLL_MASK = "[ROLL_NO]"
CNIC_MASK = "[CNIC]"
PHONE_MASK = "[PHONE]"

# LGU-style roll numbers: Fa23-BSCS-999, SP24-BSSE-001, su22 mscs 12 (separator - _ / or space).
_ROLL_RE = re.compile(r"\b(?:fa|sp|su)\d{2}[-_/ ]?[a-z]{2,6}[-_/ ]?\d{2,4}\b", re.IGNORECASE)

# CNIC: 12345-1234567-1, or 13 consecutive digits.
_CNIC_RE = re.compile(r"(?<!\d)(?:\d{5}-\d{7}-\d|\d{13})(?!\d)")

# Pakistani phone numbers: +92 / 0092 / 0 prefix, mobiles (3xx) and landlines
# (2-4 digit area code), optional spaces or dashes, and a trailing "-22" style range.
_PHONE_RE = re.compile(
    r"(?<![\w+])"
    r"(?:\+92|0092|0)[\s-]?"
    r"(?:3\d{2}[\s-]?\d{7}|\d{2,4}[\s-]?\d{6,8})"
    r"(?:-\d{1,2})?"
    r"(?!\d)"
)


def redact(text: str) -> str:
    """Replace roll numbers, CNICs and phone numbers with placeholder tokens."""
    if not text:
        return text
    text = _ROLL_RE.sub(ROLL_MASK, text)
    text = _CNIC_RE.sub(CNIC_MASK, text)
    return _PHONE_RE.sub(PHONE_MASK, text)
