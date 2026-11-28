"""Embedding providers (D17: gemini-embedding-001 at 768 dimensions, COST-2: 1 call per turn).

- GeminiEmbedder: google-genai SDK, document task type on ingest, query task type on search,
  vectors normalized (Gemini only normalizes its full 3072-dimension output).
- OpenAIEmbedder (PAID, amended D17 2026-11-28): text-embedding-3-* over plain httpx, asked
  for EMBEDDING_DIM dimensions so the vector(768) column stays. Chosen when EMBEDDING_MODEL
  starts with "text-embedding-".
- FakeEmbedder: deterministic hashed bag of words. No network, no quota. Tests and eval only.
- CachedQueryEmbedder: in-process cache for query embeddings (moves to Redis in M3).
The model name is stored with every chunk, so a model change is detectable (re-embed needed).
"""

import hashlib
import math
import re
from collections import OrderedDict
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    import httpx

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger("embeddings")

TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]


class EmbeddingError(RuntimeError):
    """Embedding failed (quota, network, provider). Callers fall back to keyword search."""


class Embedder(Protocol):
    name: str
    dim: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm > 0 else vector


_TOKEN = re.compile(r"[\w']+", re.UNICODE)


def _stem(token: str) -> str:
    """Tiny plural stripper so 'fees'/'fee' and 'policies'/'policy' share a bucket."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


class FakeEmbedder:
    """Deterministic, lexical embeddings for tests and offline eval (never for production)."""

    name = "fake-hashed-bow"

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim
        self.calls = 0

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(_stem(token).encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        return normalize(vector)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        return self._vector(text)


class GeminiEmbedder:
    """gemini-embedding-001 (or the EMBEDDING_MODEL from env) via the google-genai SDK."""

    def __init__(self, api_key: str, model: str, dim: int, batch_size: int = 16) -> None:
        from google import genai  # imported lazily: tests never construct this class

        self._client = genai.Client(api_key=api_key)
        self.name = model
        self.dim = dim
        self._batch_size = batch_size

    async def _embed(self, texts: list[str], task_type: TaskType) -> list[list[float]]:
        from google.genai import errors, types

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            try:
                response = await self._client.aio.models.embed_content(
                    model=self.name,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        task_type=task_type, output_dimensionality=self.dim
                    ),
                )
            except errors.APIError as exc:
                raise EmbeddingError(f"embedding failed with status {exc.code}") from exc
            embeddings = response.embeddings or []
            if len(embeddings) != len(batch):
                raise EmbeddingError("embedding response size mismatch")
            for item in embeddings:
                values = list(item.values or [])
                if len(values) != self.dim:
                    raise EmbeddingError(f"expected {self.dim} dimensions, got {len(values)}")
                vectors.append(normalize(values))
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]


OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


def is_openai_embedding_model(model: str | None) -> bool:
    return bool(model and model.startswith("text-embedding-"))


class OpenAIEmbedder:
    """OpenAI embeddings at a reduced dimension (text-embedding-3 models support `dimensions`).
    The same vector space serves documents and queries (no task types)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        dim: int,
        batch_size: int = 16,
        *,
        timeout_seconds: float = 25,
        client: "httpx.AsyncClient | None" = None,
    ) -> None:
        import httpx

        self._client = client or httpx.AsyncClient()
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self.name = model
        self.dim = dim
        self._batch_size = batch_size
        self._timeout = timeout_seconds

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            try:
                response = await self._client.post(
                    OPENAI_EMBEDDINGS_URL,
                    json={"model": self.name, "input": batch, "dimensions": self.dim},
                    headers=self._headers,
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                raise EmbeddingError(f"embedding failed ({type(exc).__name__})") from exc
            if response.status_code != 200:
                raise EmbeddingError(f"embedding failed with status {response.status_code}")
            data = sorted(response.json().get("data") or [], key=lambda d: d.get("index", 0))
            if len(data) != len(batch):
                raise EmbeddingError("embedding response size mismatch")
            for item in data:
                values = [float(v) for v in item.get("embedding") or []]
                if len(values) != self.dim:
                    raise EmbeddingError(f"expected {self.dim} dimensions, got {len(values)}")
                vectors.append(normalize(values))
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]


class CachedQueryEmbedder:
    """Wraps an embedder with an LRU cache for queries (repeated questions cost nothing)."""

    def __init__(self, inner: Embedder, max_items: int = 1000) -> None:
        self._inner = inner
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._max = max_items
        self.name = inner.name
        self.dim = inner.dim
        self.hits = 0

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._inner.embed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        key = " ".join(text.lower().split())
        if key in self._cache:
            self.hits += 1
            self._cache.move_to_end(key)
            return self._cache[key]
        vector = await self._inner.embed_query(text)
        self._cache[key] = vector
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)
        return vector


def build_embedder(settings: Settings) -> Embedder | None:
    """Gemini when a key and model are configured; FakeEmbedder when EMBEDDING_MODEL=fake;
    otherwise None (no vectors: keyword search only). Never mixes providers silently."""
    model = settings.embedding_model
    if model == "fake":
        return CachedQueryEmbedder(FakeEmbedder(settings.embedding_dim))
    if is_openai_embedding_model(model):
        if settings.openai_api_key:
            return CachedQueryEmbedder(
                OpenAIEmbedder(
                    settings.openai_api_key.get_secret_value(),
                    model or "",
                    settings.embedding_dim,
                    settings.embedding_batch_size,
                    timeout_seconds=settings.llm_timeout_seconds,
                )
            )
        log.warning("embeddings_disabled", reason="EMBEDDING_MODEL is OpenAI but no OPENAI_API_KEY")
        return None
    if model and settings.gemini_api_key:
        return CachedQueryEmbedder(
            GeminiEmbedder(
                settings.gemini_api_key.get_secret_value(),
                model,
                settings.embedding_dim,
                settings.embedding_batch_size,
            )
        )
    log.warning("embeddings_disabled", reason="no GEMINI_API_KEY or EMBEDDING_MODEL")
    return None
