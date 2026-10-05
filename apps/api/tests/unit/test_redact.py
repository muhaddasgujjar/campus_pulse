"""Redaction of roll numbers, CNICs and phone numbers (SEC-3, SEC-5).

All identifiers below are FAKE values in the real formats. Never use real ones.
"""

import pytest

from app.core.redact import CNIC_MASK, PHONE_MASK, ROLL_MASK, redact


@pytest.mark.parametrize(
    "roll",
    ["Fa23-BSCS-999", "FA23-BSCS-999", "sp24-bsse-001", "Su22 MSCS 12", "Fa21_BSIT_045"],
)
def test_redacts_roll_numbers(roll: str) -> None:
    assert redact(f"My roll number is {roll}, help") == f"My roll number is {ROLL_MASK}, help"


@pytest.mark.parametrize("cnic", ["12345-6789012-3", "1234567890123"])
def test_redacts_cnic(cnic: str) -> None:
    assert redact(f"CNIC {cnic}.") == f"CNIC {CNIC_MASK}."


@pytest.mark.parametrize(
    "phone",
    [
        "0300-0000000",
        "03000000000",
        "+92 300 0000000",
        "+923000000000",
        "0092-300-0000000",
        "042-00000000",
        "042-00000001-02",
    ],
)
def test_redacts_phone_numbers(phone: str) -> None:
    assert redact(f"call me at {phone} today") == f"call me at {PHONE_MASK} today"


def test_redacts_everything_in_one_message() -> None:
    text = "I am Fa23-BSCS-999, CNIC 12345-6789012-3, phone 0300-1234567."
    assert redact(text) == f"I am {ROLL_MASK}, CNIC {CNIC_MASK}, phone {PHONE_MASK}."


def test_cnic_is_not_half_redacted_as_phone() -> None:
    assert redact("1234567890123") == CNIC_MASK


@pytest.mark.parametrize(
    "safe",
    [
        "What is the fee for BSCS? It is 7744 per credit hour.",
        "Semester 3 section B timetable on 2026-10-05",
        "Room 204, CS-101 at 08:30",
        "FY 2026-27 admission fee",
        "",
    ],
)
def test_leaves_ordinary_text_alone(safe: str) -> None:
    assert redact(safe) == safe
