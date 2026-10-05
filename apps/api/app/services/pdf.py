"""PDF text extraction for uploads (DATA-3). Text PDFs only: no OCR (D2).

Checks before parsing: size limit and the %PDF- magic bytes. Encrypted PDFs are rejected.
A PDF with almost no extractable text is treated as image-only and rejected, so an admin types
the content in by hand instead (D2). pypdf is used because it is pure Python, small and BSD
licensed, which keeps the image inside Render's 512 MB.
"""

import io
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MIN_CHARS_PER_PAGE = 40


class PdfRejectedError(ValueError):
    """The upload is not an acceptable text PDF. The message is safe to show to staff."""


@dataclass(frozen=True)
class ExtractedPdf:
    text: str
    pages: int


def extract_pdf_text(data: bytes, max_mb: int) -> ExtractedPdf:
    if len(data) > max_mb * 1024 * 1024:
        raise PdfRejectedError(f"File is larger than {max_mb} MB.")
    if not data.startswith(b"%PDF-"):
        raise PdfRejectedError("File is not a PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise PdfRejectedError("Password-protected PDFs are not supported.")
        pages = [page.extract_text() or "" for page in reader.pages]
    except PyPdfError as exc:
        raise PdfRejectedError("The PDF could not be read.") from exc

    text = "\n\n".join(p.strip() for p in pages if p.strip())
    if len(text) < MIN_CHARS_PER_PAGE * max(len(pages), 1) / 2:
        raise PdfRejectedError(
            "This PDF has little or no text (it looks scanned). OCR is not supported: "
            "please type the content in as a knowledge entry."
        )
    return ExtractedPdf(text=text, pages=len(pages))
