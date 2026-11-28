"""Which uploads are accepted and how their text is read (DATA-3): text PDFs and Word (.docx).

The declared content type picks the extractor, and each extractor checks the file's own
signature, so a file renamed to another type is refused.
"""

from app.services.docx import extract_docx_text
from app.services.pdf import ExtractedText, UploadRejectedError, extract_pdf_text

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ACCEPTED = (PDF_MIME, DOCX_MIME)
EXTENSIONS = {".pdf": PDF_MIME, ".docx": DOCX_MIME}

__all__ = ["ACCEPTED", "DOCX_MIME", "EXTENSIONS", "PDF_MIME", "UploadRejectedError",
           "extract_upload"]  # fmt: skip


def extract_upload(data: bytes, content_type: str, max_mb: int) -> ExtractedText:
    if content_type == PDF_MIME:
        return extract_pdf_text(data, max_mb)
    if content_type == DOCX_MIME:
        return extract_docx_text(data, max_mb)
    raise UploadRejectedError("Upload a PDF or Word (.docx) file.")
