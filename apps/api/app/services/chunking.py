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


def _blocks(text: str) -> list[str]:
    """Paragraph blocks; a heading starts a new block and stays attached to what follows."""
    blocks: list[str] = []
    current: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.strip():
            if current:
                blocks.append(" ".join(current))
                current = []
            continue
        if _is_heading(line) and current:
            blocks.append(" ".join(current))
            current = []
        current.append(line.strip())
    if current:
        blocks.append(" ".join(current))
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
    for block in blocks:
        words = block.split()
        if current and len(current) + len(words) > max_words:
            chunks.append(current)
            current = current[-overlap_words:] if overlap_words else []
        current.extend(words)
        if len(current) >= target_words:
            chunks.append(current)
            current = current[-overlap_words:] if overlap_words else []
    if current and (not chunks or len(current) > overlap_words):
        chunks.append(current)
    return [" ".join(words) for words in chunks if words]


def entry_chunk(title: str, question: str | None, answer: str) -> str:
    """A knowledge base entry is one chunk: title, question and answer together."""
    parts = [title.strip()]
    if question and question.strip():
        parts.append(f"Q: {question.strip()}")
    parts.append(f"A: {answer.strip()}")
    return "\n".join(parts)
