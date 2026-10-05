"""Voice provider interfaces (D18, VOI-1, VOI-2, COST-9).

Voice runs in the browser (Web Speech API, speechSynthesis). The server only offers a
fallback transcription (Gemini audio input, in memory) built in M4. Audio is never stored.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class STTProvider(Protocol):
    """Speech to text. Server-side use is the fallback path only (POST /api/voice/transcribe)."""

    name: str

    async def transcribe(self, audio: bytes, mime_type: str, language_hint: str | None) -> str:
        """Return the transcript. Audio bytes stay in memory and are discarded after the call."""
        ...


@runtime_checkable
class TTSProvider(Protocol):
    """Text to speech. The default implementation lives in the browser (speechSynthesis)."""

    name: str

    async def synthesize(self, text: str, language: str) -> bytes:
        """Return audio for `text`. Not used server-side in the MVP."""
        ...


__all__ = ["STTProvider", "TTSProvider"]
