"""Word (.docx) text extraction for uploads (DATA-3). Written before the code."""

import io
import zipfile

import pytest

from app.services.docx import extract_docx_text
from app.services.uploads import DOCX_MIME, PDF_MIME, UploadRejectedError, extract_upload
from tests.support.docx import make_docx, paragraph, table
from tests.support.pdf import make_pdf

POLICY = [
    "LGU Hostel SOP",
    "Hostel gates close at 22:00 every night.",
    "Guests may visit the lounge from 16:00 to 19:00 on Sundays.",
]


def test_paragraphs_and_tables_keep_their_order() -> None:
    body = (
        paragraph("Hostel fees for 2026-27")
        + table([["Room", "Fee per semester"], ["Shared", "Rs 45,000"], ["Single", "Rs 60,000"]])
        + paragraph("Pay at the Accounts Office before the semester starts.")
    )
    text = extract_docx_text(make_docx(body), max_mb=10).text
    lines = text.splitlines()
    assert lines[0] == "Hostel fees for 2026-27"
    assert "Room | Fee per semester" in lines
    assert "Shared | Rs 45,000" in lines
    assert lines[-1] == "Pay at the Accounts Office before the semester starts."


def test_tabs_and_line_breaks_become_whitespace() -> None:
    text = extract_docx_text(
        make_docx(paragraphs=["Office\tRoom 12\nMonday to Friday, 08:00 to 16:00 every week"]),
        max_mb=10,
    ).text
    assert "Office\tRoom 12\nMonday to Friday" in text


def test_pages_are_unknown_for_word_files() -> None:
    assert extract_docx_text(make_docx(paragraphs=POLICY), max_mb=10).pages is None


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"not a zip at all, just text", "not a Word"),
        (make_pdf(POLICY), "not a Word"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100, "Password-protected or old"),
    ],
)
def test_files_that_are_not_docx_are_refused(data: bytes, message: str) -> None:
    with pytest.raises(UploadRejectedError, match=message):
        extract_docx_text(data, max_mb=10)


def test_a_zip_without_a_word_document_is_refused() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(UploadRejectedError, match="not a Word"):
        extract_docx_text(buffer.getvalue(), max_mb=10)


def test_macro_enabled_documents_are_refused() -> None:
    data = make_docx(paragraphs=POLICY, extra_files={"word/vbaProject.bin": b"\x00" * 64})
    with pytest.raises(UploadRejectedError, match="macros"):
        extract_docx_text(data, max_mb=10)


def test_a_doctype_is_refused() -> None:
    xml = (
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>"
    )
    with pytest.raises(UploadRejectedError, match="could not be read"):
        extract_docx_text(make_docx(document_xml=xml), max_mb=10)


def test_a_zip_bomb_is_refused_before_it_is_unpacked() -> None:
    huge = paragraph("x" * 1000) * 60_000  # about 60 MB of XML, compresses to well under 1 MB
    data = make_docx(huge)
    assert len(data) < 1024 * 1024
    with pytest.raises(UploadRejectedError, match="too large when unpacked"):
        extract_docx_text(data, max_mb=10)


def test_an_empty_document_is_refused() -> None:
    with pytest.raises(UploadRejectedError, match="little or no text"):
        extract_docx_text(make_docx(paragraphs=["Hi"]), max_mb=10)


def test_the_size_limit_applies() -> None:
    with pytest.raises(UploadRejectedError, match="larger than 1 MB"):
        extract_docx_text(b"PK\x03\x04" + b"\x00" * (1024 * 1024 + 1), max_mb=1)


# --- choosing the extractor -----------------------------------------------------------------


def test_extract_upload_picks_the_extractor_by_content_type() -> None:
    assert "22:00" in extract_upload(make_docx(paragraphs=POLICY), DOCX_MIME, 10).text
    assert "22:00" in extract_upload(make_pdf(POLICY * 3), PDF_MIME, 10).text


def test_extract_upload_refuses_other_types() -> None:
    with pytest.raises(UploadRejectedError, match="PDF or Word"):
        extract_upload(b"hello", "text/plain", 10)


def test_a_word_file_sent_as_a_pdf_is_refused() -> None:
    with pytest.raises(UploadRejectedError, match="not a PDF"):
        extract_upload(make_docx(paragraphs=POLICY), PDF_MIME, 10)


def test_a_doctype_hidden_after_a_long_comment_is_refused() -> None:
    xml = (
        '<?xml version="1.0"?><!--' + "x" * 10_000 + '--><!DOCTYPE x [<!ENTITY a "a">]>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>"
    )
    with pytest.raises(UploadRejectedError, match="could not be read"):
        extract_docx_text(make_docx(document_xml=xml), max_mb=10)
