"""POST /api/voice/transcribe: server fallback transcription (VOI-1, D18, COST-9, SEC-2).

Only browsers without speech recognition call this. The body is the raw recording, with its
Content-Type (for example `audio/webm;codecs=opus`): no multipart parsing, no temp files. The
audio is checked (size, declared type, file signature), transcribed in memory and discarded.
It is never stored and never logged. The browser stops recording at 60 seconds.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import chat_services, read_capped
from app.core.logging import get_logger
from app.services.chat import ChatServices
from app.services.voice.transcribe import GEMINI_MIME, STTError, STTQuotaError, check_audio

router = APIRouter(prefix="/api/voice", tags=["voice"])
log = get_logger("voice")


class TranscriptOut(BaseModel):
    transcript: str


@router.post("/transcribe", response_model=TranscriptOut)
async def transcribe(
    request: Request,
    services: Annotated[ChatServices, Depends(chat_services)],
    lang: Literal["en", "ur"] | None = None,
) -> TranscriptOut:
    client = request.client.host if request.client else "unknown"
    if not (await services.rate_limiter.hit(f"voice:{client}")).allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many requests")
    if services.stt is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "voice transcription not configured"
        )
    audio = await read_capped(
        request, services.settings.voice_max_mb * 1024 * 1024, "recording too large"
    )
    if not audio:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty recording")
    try:
        family = check_audio(audio, request.headers.get("content-type"))
    except ValueError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    try:
        text = await services.stt.transcribe(audio, GEMINI_MIME[family], lang)
    except STTQuotaError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "transcription busy") from exc
    except STTError as exc:
        log.warning("voice_transcribe_failed", error=str(exc))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "transcription failed") from exc
    finally:
        del audio  # never kept beyond this request (COST-9)
    log.info("voice_transcribed", chars=len(text))  # length only: no audio, no transcript
    return TranscriptOut(transcript=text[: services.settings.chat_max_message_chars])
