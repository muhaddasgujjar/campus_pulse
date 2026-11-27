"""Post-check (0 invented numbers), template answers and the response cache. FAKE data only."""

from datetime import date

from app.agent import templates
from app.agent.cache import CachedAnswer, InMemoryResponseCache, cache_key, normalize_query
from app.agent.postcheck import check_llm_answer, ensure_required_notes, numbers_in
from app.tools.base import Source, ToolResult

TODAY = date(2026, 10, 5)


def _fee() -> ToolResult:
    return ToolResult(
        tool="get_fee",
        data=[{"program_group": "BS Test", "level": "Undergraduate", "fiscal_year": "2026-27",
               "admission_fee": 10000.0, "tuition_per_credit_hour": 1234.0,
               "misc_per_semester": None, "notes": None}],
        sources=[Source(title="Test fee page (FY 2026-27)", office="Test Accounts Office",
                        last_verified=date(2026, 9, 1))],
        last_verified=date(2026, 9, 1),
    )  # fmt: skip


def _passed_date() -> ToolResult:
    return ToolResult(
        tool="get_key_dates",
        data=[{"title": "Test deadline", "date": date(2026, 10, 2), "passed": True,
               "days_left": -3, "office": "Test Admission Office"}],
        sources=[Source(title="Test calendar", office="Test Admission Office")],
    )  # fmt: skip


def test_numbers_are_normalized() -> None:
    assert numbers_in("Rs 1,234.00 and 007 and 2026-27") == {"1234", "7", "2026", "27"}


def test_answer_using_only_data_numbers_passes() -> None:
    answer = "For BS Test (FY 2026-27) tuition is Rs 1,234 per credit hour. Verified 1 Sep 2026."
    check = check_llm_answer(answer, [_fee()], "what is the fee", TODAY)
    assert check.ok and not check.invented


def test_invented_number_is_caught() -> None:
    answer = "Tuition is Rs 1,500 per credit hour (FY 2026-27)."
    check = check_llm_answer(answer, [_fee()], "what is the fee", TODAY)
    assert not check.ok
    assert check.invented == {"1500"}


def test_numbers_from_the_question_and_today_are_allowed() -> None:
    answer = "For 18 credit hours, see the fee page. Today is 5 Oct."
    check = check_llm_answer(answer, [_fee()], "fee for 18 credit hours", TODAY)
    assert check.ok


def test_no_answer_signal_is_not_ok_but_not_invented() -> None:
    check = check_llm_answer("NO_ANSWER", [_fee()], "q", TODAY)
    assert not check.ok and not check.invented


def test_missing_fiscal_year_and_passed_notice_are_appended() -> None:
    text = ensure_required_notes("Tuition is Rs 1,234 per credit hour.", [_fee(), _passed_date()])
    assert "(Fee figures are for FY 2026-27.)" in text
    assert "This date has passed. Please confirm with the Test Admission Office." in text


def test_fee_template_states_year_unit_and_omits_missing_fields() -> None:
    text = templates.structured_answer(_fee())
    assert "FY 2026-27" in text
    assert "Rs 1,234 per credit hour" in text
    assert "Rs 10,000" in text
    assert "miscellaneous" not in text  # missing in the data: never guessed
    assert (
        "Source: Test fee page (FY 2026-27) · Test Accounts Office · last verified Tue, 1 Sep 2026"
    ) in text


def test_key_date_template_says_passed_and_names_the_office() -> None:
    text = templates.structured_answer(_passed_date())
    assert "Test deadline: Fri, 2 Oct 2026." in text
    assert "This date has passed. Please confirm with the Test Admission Office." in text


def test_expired_source_is_flagged() -> None:
    result = _fee()
    result.sources = [Source(title="Old page", expired=True)]
    assert "may be outdated" in templates.source_line(result)


def test_extractive_answer_quotes_the_answer_part() -> None:
    result = ToolResult(
        tool="search_knowledge",
        data=[{"title": "Test hostel", "content": "Test hostel\nQ: Rooms?\nA: Two per room.",
               "owner": "Test Hostel Office"}],
        sources=[Source(title="Test hostel", office="Test Hostel Office")],
    )  # fmt: skip
    text = templates.extractive_answer(result, "rooms")
    assert text.startswith('According to "Test hostel" (Test Hostel Office):\nTwo per room.')


def test_extractive_answer_quotes_the_chunk_and_lines_that_match_the_question() -> None:
    notes = "Fee notes\n" + "\n".join(
        f"Note {n}: security deposit is refundable." for n in range(40)
    )
    table = "Fee tables\n" + "\n".join(
        [*(f"Program Alpha row {n} | 1,111" for n in range(30)),
         "Test Social Sciences | Tuition Fee (Per Credit Hour) | 2,222",
         *(f"Program Beta row {n} | 3,333" for n in range(30))]
    )  # fmt: skip
    result = ToolResult(
        tool="search_knowledge",
        data=[{"title": "Test fees", "content": notes, "owner": "Test Office"},
              {"title": "Test fees", "content": table, "owner": "Test Office"}],
        sources=[Source(title="Test fees", office="Test Office")],
    )  # fmt: skip
    text = templates.extractive_answer(result, "tuition per credit hour for social sciences")
    assert "Test Social Sciences | Tuition Fee (Per Credit Hour) | 2,222" in text
    assert "security deposit" not in text
    assert len(text) < 900


def test_fallback_names_the_office_contact() -> None:
    office = {"name": "Test Office", "phones": ["000-0000000"], "email": "test@example.edu"}
    text = templates.fallback_text(office)
    assert text.startswith("I don't have verified information on this.")
    assert "Test Office can help: 000-0000000; test@example.edu." in text


# --- response cache (COST-3) ---------------------------------------------------------------


def test_cache_key_depends_on_language_program_data_version_and_today() -> None:
    day = date(2026, 10, 5)
    base = cache_key(normalize_query("  What is the FEE? "), "en", None, "v1", day)
    assert base == cache_key("what is the fee", "en", None, "v1", day)
    assert base != cache_key("what is the fee", "roman_ur", None, "v1", day)
    assert base != cache_key("what is the fee", "en", "BSCS", "v1", day)
    assert base != cache_key("what is the fee", "en", None, "v2", day)
    assert base != cache_key("what is the fee", "en", None, "v1", date(2026, 10, 6))


async def test_cache_ttl_and_size_limit() -> None:
    now = [0.0]
    cache = InMemoryResponseCache(ttl_seconds=10, max_items=2, clock=lambda: now[0])
    answer = CachedAnswer("a", [], None)
    await cache.set("k1", answer)
    await cache.set("k2", answer)
    await cache.set("k3", answer)  # evicts k1
    assert await cache.get("k1") is None
    assert await cache.get("k3") == answer
    now[0] = 11
    assert await cache.get("k3") is None
