"""Word (.docx) text extraction for uploads (DATA-3). Text only: images are ignored (no OCR, D2).

A .docx file is a zip archive; the body text is in `word/document.xml`. This module reads it
with the standard library (zipfile and ElementTree) instead of python-docx, which would add
lxml, a large native dependency, to an image that must fit Render's 512 MB.

Checks, in order, before any XML is parsed:
- size limit and the zip signature (a password-protected or old .doc file is an OLE file,
  refused with its own message),
- the archive must contain `word/document.xml`; macro-enabled documents (`vbaProject.bin`)
  are refused,
- zip bomb guard: the declared unpacked size of the whole archive and of document.xml is
  capped, and document.xml is read with a hard limit,
- no DOCTYPE in document.xml (no entity tricks; the bundled expat also blocks billion laughs).
Headers, footers, comments and tracked deletions are not read: only the body text.
"""

import io
import re
import zipfile
from xml.etree import ElementTree

from app.services.pdf import ExtractedText, UploadRejectedError

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # old .doc, or an encrypted .docx
UNPACKED_LIMIT_FACTOR = 5  # unpacked archive may be at most 5x the upload limit
MIN_CHARS = 40


def _paragraph_text(p: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in p.iter():
        if node.tag == f"{W}t" and node.text:
            parts.append(node.text)
        elif node.tag == f"{W}tab":
            parts.append("\t")
        elif node.tag in (f"{W}br", f"{W}cr"):
            parts.append("\n")
        elif node.tag == f"{W}delText":  # tracked deletion: not part of the document
            continue
    return "".join(parts).strip()


def _table_lines(tbl: ElementTree.Element) -> list[str]:
    lines = []
    for row in tbl.iter(f"{W}tr"):
        cells = [
            " ".join(t for t in (_paragraph_text(p) for p in cell.iter(f"{W}p")) if t)
            for cell in row.iter(f"{W}tc")
        ]
        if any(cells):
            lines.append(" | ".join(cells))
    return lines


def _body_lines(root: ElementTree.Element) -> list[str]:
    body = root.find(f"{W}body")
    if body is None:
        raise UploadRejectedError("The Word file could not be read.")
    lines: list[str] = []
    for child in body:  # paragraphs and tables in document order
        if child.tag == f"{W}p":
            text = _paragraph_text(child)
            if text:
                lines.append(text)
        elif child.tag == f"{W}tbl":
            lines.extend(_table_lines(child))
        elif child.tag == f"{W}sdt":  # content controls wrap ordinary paragraphs
            lines.extend(t for t in (_paragraph_text(p) for p in child.iter(f"{W}p")) if t)
    return lines


def extract_docx_text(data: bytes, max_mb: int) -> ExtractedText:
    limit = max_mb * 1024 * 1024
    if len(data) > limit:
        raise UploadRejectedError(f"File is larger than {max_mb} MB.")
    if data.startswith(OLE_MAGIC):
        raise UploadRejectedError(
            "Password-protected or old Word files (.doc) are not supported. "
            "Remove the password or save it as .docx or PDF."
        )
    if not data.startswith(ZIP_MAGIC):
        raise UploadRejectedError("File is not a Word document (.docx).")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = {info.filename: info for info in archive.infolist()}
    except (zipfile.BadZipFile, ValueError) as exc:
        raise UploadRejectedError("File is not a Word document (.docx).") from exc

    entry = names.get("word/document.xml")
    if entry is None:
        raise UploadRejectedError("File is not a Word document (.docx).")
    if any(name.lower().endswith("vbaproject.bin") for name in names):
        raise UploadRejectedError("Word files with macros are not accepted. Save it as .docx.")
    unpacked_limit = limit * UNPACKED_LIMIT_FACTOR
    if (
        sum(info.file_size for info in names.values()) > unpacked_limit
        or entry.file_size > unpacked_limit
    ):
        raise UploadRejectedError("The Word file is too large when unpacked.")

    try:
        with archive.open(entry) as handle:
            xml = handle.read(unpacked_limit + 1)  # declared sizes can lie: cap the read too
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise UploadRejectedError("The Word file could not be read.") from exc
    if len(xml) > unpacked_limit:
        raise UploadRejectedError("The Word file is too large when unpacked.")
    # Real Word files never declare a DOCTYPE or entities. Scan the whole file: comments
    # before a DOCTYPE could push it past any fixed prefix.
    if re.search(rb"<!(DOCTYPE|ENTITY)", xml, re.IGNORECASE):
        raise UploadRejectedError("The Word file could not be read.")
    try:
        # Safe here: no DOCTYPE or entities (checked above), and the bundled expat (2.4.1+)
        # also refuses entity expansion attacks.
        root = ElementTree.fromstring(xml)  # noqa: S314
    except ElementTree.ParseError as exc:
        raise UploadRejectedError("The Word file could not be read.") from exc

    text = "\n".join(_body_lines(root)).strip()
    if len(text) < MIN_CHARS:
        raise UploadRejectedError(
            "This Word file has little or no text. Pictures of text can't be read (no OCR): "
            "please type the content in as a knowledge entry."
        )
    return ExtractedText(text=text, pages=None)
