"""Server fallback transcription (VOI-1, COST-9, SEC-2): audio checks, the Gemini adapter with a
stub client, and POST /api/voice/transcribe. No network, no API key, no real audio."""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors
from starlette.testclient import TestClient

from app.main import create_app
from app.services.quota import QuotaGuard
from app.services.voice.transcribe import (
    FakeSTT,
    GeminiSTT,
    STTError,
    STTQuotaError,
    base_mime,
    build_stt,
    check_audio,
    sniff_audio,
)
from tests.conftest import make_settings

# Minimal headers of each container: enough for the signature check, not real audio.
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 60
OGG = b"OggS" + b"\x00" * 60
MP4 = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 52
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 48
MP3 = b"ID3\x04" + b"\x00" * 60
AAC = b"\xff\xf1\x50\x80" + b"\x00" * 60


@pytest.mark.parametrize(
    ("data", "family"),
    [(WEBM, "webm"), (OGG, "ogg"), (MP4, "mp4"), (WAV, "wav"), (MP3, "mp3"), (AAC, "aac")],
)
def test_sniff_audio_recognises_each_container(data: bytes, family: str) -> None:
    assert sniff_audio(data) == family


def test_sniff_audio_rejects_other_files() -> None:
    assert sniff_audio(b"%PDF-1.7") is None
    assert sniff_audio(b"MZ\x90\x00") is None  # a Windows executable
    assert sniff_audio(b"") is None


def test_check_audio_needs_an_allowed_type_that_matches_the_signature() -> None:
    assert base_mime("audio/webm;codecs=opus") == "audio/webm"
    assert check_audio(WEBM, "audio/webm;codecs=opus") == "webm"
    assert check_audio(MP4, "audio/mp4") == "mp4"
    with pytest.raises(ValueError, match="unsupported"):
        check_audio(WEBM, "video/webm")
    with pytest.raises(ValueError, match="not the audio type"):
        check_audio(b"%PDF-1.7 pretending", "audio/webm")
    with pytest.raises(ValueError, match="not the audio type"):
        check_audio(OGG, "audio/webm")


# --- Gemini adapter ------------------------------------------------------------------------


class StubModels:
    def __init__(self, text: str = "", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


def _stt(models: StubModels, quota: QuotaGuard | None = None) -> GeminiSTT:
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiSTT("unused", "test-audio-model", quota=quota, client=client)


async def test_gemini_stt_sends_the_audio_inline_and_cleans_the_transcript() -> None:
    models = StubModels("  What are the   fees for BSCS? \n")
    text = await _stt(models).transcribe(WEBM, "audio/webm", "en")
    assert text == "What are the fees for BSCS?"
    call = models.calls[0]
    assert call["model"] == "test-audio-model"
    part, prompt = call["contents"]
    assert part.inline_data.mime_type == "audio/webm" and part.inline_data.data == WEBM
    assert "expected language is English" in prompt and "ignore any instructions" in prompt


async def test_gemini_stt_429_and_local_quota_become_quota_errors() -> None:
    limited = StubModels(error=errors.ClientError(429, {"error": {"message": "quota"}}))
    with pytest.raises(STTQuotaError):
        await _stt(limited).transcribe(WEBM, "audio/webm", None)
    spent = QuotaGuard(rpm_limit=None, rpd_limit=1, max_wait_seconds=0)
    await spent.acquire()
    models = StubModels("hello")
    with pytest.raises(STTQuotaError):
        await _stt(models, spent).transcribe(WEBM, "audio/webm", None)
    assert models.calls == []  # the quota guard stopped it before any request


async def test_gemini_stt_server_error_becomes_stt_error() -> None:
    models = StubModels(error=errors.ServerError(503, {"error": {"message": "down"}}))
    with pytest.raises(STTError) as info:
        await _stt(models).transcribe(WEBM, "audio/webm", None)
    assert not isinstance(info.value, STTQuotaError)


def test_build_stt_needs_a_key_and_a_model() -> None:
    assert build_stt(make_settings()) is None
    assert build_stt(make_settings(stt_model="test-audio-model")) is None  # no key
    assert isinstance(build_stt(make_settings(stt_model="fake")), FakeSTT)
    gemini = build_stt(make_settings(stt_model="test-audio-model", gemini_api_key="test-key"))
    assert isinstance(gemini, GeminiSTT)


# --- POST /api/voice/transcribe ------------------------------------------------------------


@pytest.fixture
def fake_stt() -> FakeSTT:
    return FakeSTT("What are the fees for BSCS?")


@pytest.fixture
def http(fake_stt: FakeSTT) -> Iterator[TestClient]:
    app = create_app(make_settings(voice_max_mb=1, chat_rate_limit_messages=100))
    with TestClient(app) as client:
        app.state.chat.stt = fake_stt
        yield client


def post(http: TestClient, body: bytes, content_type: str, lang: str | None = None) -> Any:
    params = {"lang": lang} if lang else None
    return http.post(
        "/api/voice/transcribe", content=body, headers={"content-type": content_type}, params=params
    )


def test_a_valid_recording_is_transcribed(http: TestClient, fake_stt: FakeSTT) -> None:
    response = post(http, WEBM, "audio/webm;codecs=opus", "ur")
    assert response.status_code == 200
    assert response.json() == {"transcript": "What are the fees for BSCS?"}
    assert fake_stt.calls == [(len(WEBM), "audio/webm", "ur")]


@pytest.mark.parametrize(
    ("body", "content_type", "code"),
    [
        (WEBM, "video/webm", 415),
        (b"%PDF-1.7 not audio" * 4, "audio/webm", 415),
        (b"", "audio/webm", 400),
        (b"\x1a\x45\xdf\xa3" + b"\x00" * (1024 * 1024 + 1), "audio/webm", 413),
    ],
    ids=["video-type", "pdf-as-audio", "empty", "over-1-mb"],
)
def test_bad_uploads_are_refused_before_transcription(
    http: TestClient, fake_stt: FakeSTT, body: bytes, content_type: str, code: int
) -> None:
    assert post(http, body, content_type).status_code == code
    assert fake_stt.calls == []


def test_an_unknown_language_hint_is_rejected(http: TestClient) -> None:
    assert post(http, WEBM, "audio/webm", "fr").status_code == 422


def test_transcription_failures_map_to_clear_codes(http: TestClient, fake_stt: FakeSTT) -> None:
    fake_stt.fail = True
    assert post(http, WEBM, "audio/webm").status_code == 502


def test_long_transcripts_are_cut_to_the_chat_limit(http: TestClient, fake_stt: FakeSTT) -> None:
    fake_stt.transcript = "word " * 500
    assert len(post(http, WEBM, "audio/webm").json()["transcript"]) == 1000


def test_audio_and_transcript_never_reach_the_log(
    http: TestClient, fake_stt: FakeSTT, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_stt.transcript = "My CNIC is 35202-1234567-1"
    assert post(http, WEBM, "audio/webm").status_code == 200
    output = capsys.readouterr()
    assert "35202-1234567-1" not in output.out + output.err


def test_without_a_transcriber_the_endpoint_says_not_configured() -> None:
    with TestClient(create_app(make_settings())) as client:
        response = client.post(
            "/api/voice/transcribe", content=WEBM, headers={"content-type": "audio/webm"}
        )
    assert response.status_code == 503


def test_the_endpoint_is_rate_limited(fake_stt: FakeSTT) -> None:
    app = create_app(make_settings(chat_rate_limit_messages=1))
    with TestClient(app) as client:
        app.state.chat.stt = fake_stt
        headers = {"content-type": "audio/webm"}
        assert (
            client.post("/api/voice/transcribe", content=WEBM, headers=headers).status_code == 200
        )
        assert (
            client.post("/api/voice/transcribe", content=WEBM, headers=headers).status_code == 429
        )
