"""Build tiny Word (.docx) files in memory for tests (no binary fixtures in git)."""

import io
import zipfile

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _run(text: str) -> str:
    parts = []
    for i, line in enumerate(text.split("\n")):
        if i:
            parts.append("<w:r><w:br/></w:r>")
        cells = line.split("\t")
        for j, cell in enumerate(cells):
            if j:
                parts.append("<w:r><w:tab/></w:r>")
            parts.append(f'<w:r><w:t xml:space="preserve">{cell}</w:t></w:r>')
    return "".join(parts)


def paragraph(text: str) -> str:
    return f"<w:p>{_run(text)}</w:p>"


def table(rows: list[list[str]]) -> str:
    body = "".join(
        "<w:tr>" + "".join(f"<w:tc>{paragraph(c)}</w:tc>" for c in row) + "</w:tr>" for row in rows
    )
    return f"<w:tbl>{body}</w:tbl>"


def make_docx(
    body_xml: str | None = None,
    *,
    paragraphs: list[str] | None = None,
    extra_files: dict[str, bytes] | None = None,
    document_xml: str | None = None,
) -> bytes:
    """A minimal valid .docx. Give `paragraphs`, raw `body_xml`, or a whole `document_xml`."""
    if document_xml is None:
        inner = body_xml if body_xml is not None else "".join(map(paragraph, paragraphs or []))
        document_xml = (
            f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}>'
            f"<w:body>{inner}</w:body></w:document>"
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        z.writestr("word/document.xml", document_xml)
        for name, data in (extra_files or {}).items():
            z.writestr(name, data)
    return buffer.getvalue()
