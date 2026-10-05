"""Log lines never contain personal identifiers (SEC-3)."""

import json

import pytest

from app.core.logging import configure_logging, get_logger


def test_log_values_are_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    get_logger("test").info("user_message", text="I am Fa23-BSCS-999, call 0300-0000000")
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["text"] == "I am [ROLL_NO], call [PHONE]"
    assert line["level"] == "info"
