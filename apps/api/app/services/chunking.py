"""Chunking (Architectural.md Section 7): split by headings and paragraphs into chunks of about
400 to 600 tokens with 10 to 15% overlap. A Q&A entry is always exactly one chunk.

Tokens are approximated as words x 1.3 (no tokenizer download, fits the 512 MB server).
"""

import re

WORDS_PER_TOKEN = 1 / 1.3
TARGET_TOKENS = 500
MAX_TOKENS = 600
OVERLAP_RATIO = 0.12

_HEADING = re.compile(
    r"^\s*(#{1,6}\s+.+|(\d+(\.\d+)*[.)]?\s+)[A-Z].{0,80}|[A-Z][A-Z0-9 ,&()/-]{3,80})\s*$"
)
URDU_FULL_STOP = chr(0x06D4)  # Urdu full stop, kept as a code point so the source is ASCII
_SENTENCE_END = re.compile(rf"(?<=[.!?{URDU_FULL_STOP}])\s+")


def _tokens(words: int) -> int:
    return round(words / WORDS_PER_TOKEN)


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and len(stripped) <= 90 and bool(_HEADING.match(stripped))


def _is_row(line: str) -> bool:
    """A table row from the web import or a PDF table: cells separated by " | "."""
    return " | " in line


def _blocks(text: str) -> list[str]:
    """Paragraph blocks; a heading starts a new block and stays attached to what follows.
    Every table row is its own block, so rows keep their line breaks."""
    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            blocks.append(" ".join(current))
            current.clear()

    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.strip():
            flush()
            continue
        if _is_row(line):
            flush()
            blocks.append(line.strip())
            continue
        if _is_heading(line) and current:
            flush()
        current.append(line.strip())
    flush()
    return blocks


def _split_long(block: str, max_words: int) -> list[str]:
    """Split one oversized paragraph at sentence boundaries (or words as a last resort)."""
    pieces: list[str] = []
    current: list[str] = []
    for sentence in _SENTENCE_END.split(block):
        words = sentence.split()
        if len(words) > max_words:
            for start in range(0, len(words), max_words):
                pieces.append(" ".join(words[start : start + max_words]))
            continue
        if sum(len(s.split()) for s in current) + len(words) > max_words and current:
            pieces.append(" ".join(current))
            current = []
        current.append(sentence)
    if current:
        pieces.append(" ".join(current))
    return pieces


def _join(units: list[str]) -> str:
    """Prose joins with spaces (PDF lines wrap mid-sentence); table rows keep their lines."""
    out = ""
    for unit in units:
        if out:
            out += "\n" if _is_row(unit) or _is_row(out.rsplit("\n", 1)[-1]) else " "
        out += unit
    return out


def _words(units: list[str]) -> int:
    return sum(len(u.split()) for u in units)


def _overlap(units: list[str], overlap_words: int) -> list[str]:
    """Tail of a finished chunk carried into the next one: whole table rows, or the last
    words of a paragraph."""
    if not overlap_words or not units:
        return []
    if not _is_row(units[-1]):
        return [" ".join(units[-1].split()[-overlap_words:])]
    carried: list[str] = []
    for unit in reversed(units):
        if not _is_row(unit) or _words([unit, *carried]) > overlap_words:
            break
        carried.insert(0, unit)
    return carried


def chunk_text(
    text: str,
    target_tokens: int = TARGET_TOKENS,
    max_tokens: int = MAX_TOKENS,
    overlap_ratio: float = OVERLAP_RATIO,
) -> list[str]:
    target_words = int(target_tokens * WORDS_PER_TOKEN)
    max_words = int(max_tokens * WORDS_PER_TOKEN)
    overlap_words = int(target_words * overlap_ratio)

    blocks: list[str] = []
    for block in _blocks(text):
        blocks.extend(_split_long(block, max_words) if len(block.split()) > max_words else [block])

    chunks: list[list[str]] = []
    current: list[str] = []
    caption: list[str] = []  # short lines just above the table being chunked
    recent: list[str] = []  # short non-row lines seen since the last table row

    def start_next(carried: list[str], next_block: str | None) -> list[str]:
        # A chunk that starts inside a table repeats the table's caption, so every row
        # stays next to what it describes (for example which faculty a fee row belongs to).
        if next_block is not None and _is_row(next_block) and caption:
            missing = [c for c in caption if c not in carried]
            if _words([*missing, *carried]) < max_words // 2:
                return [*missing, *carried]
        return carried

    for index, block in enumerate(blocks):
        if _is_row(block):
            if recent:
                caption, recent = recent[-2:], []
        elif len(block.split()) <= 20:
            recent.append(block)
        else:
            recent = []
        words = len(block.split())
        if current and _words(current) + words > max_words:
            chunks.append(current)
            current = start_next(_overlap(current, overlap_words), block)
        current.append(block)
        if _words(current) >= target_words:
            chunks.append(current)
            following = blocks[index + 1] if index + 1 < len(blocks) else None
            current = start_next(_overlap(current, overlap_words), following)
    if current and (not chunks or _words(current) > overlap_words):
        chunks.append(current)
    return [_join(units) for units in chunks if units]


def entry_chunk(title: str, question: str | None, answer: str) -> str:
    """A knowledge base entry is one chunk: title, question and answer together."""
    parts = [title.strip()]
    if question and question.strip():
        parts.append(f"Q: {question.strip()}")
    parts.append(f"A: {answer.strip()}")
    return "\n".join(parts)
