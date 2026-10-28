import hashlib
import json
import math
import os
import re
import threading
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_embedding_text(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(
        " ", unicodedata.normalize("NFKC", text)
    ).strip()


def content_hash(text: str) -> str:
    normalized = normalize_embedding_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class EmbeddingProvider(Protocol):
    model_id: str
    model_version: str

    def embed(self, text: str) -> Sequence[float]:
        ...


@dataclass(frozen=True)
class EmbeddingRecord:
    paper_id: str
    model_id: str
    model_version: str
    dimension: int
    content_hash: str
    embedding: tuple[float, ...]


class HostedEmbeddingProvider:
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model_id: str,
        model_version: str = "unspecified",
        timeout_seconds: float = 15,
    ):
        if not endpoint.strip() or not api_key.strip() or not model_id.strip():
            raise ValueError("Embedding endpoint, API key, and model ID are required.")
        if timeout_seconds <= 0:
            raise ValueError("Embedding timeout must be positive.")
        self.endpoint = endpoint
        self._api_key = api_key
        self.model_id = model_id
        self.model_version = model_version
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "HostedEmbeddingProvider":
        endpoint = os.getenv("EMBEDDING_API_URL", "")
        api_key = os.getenv("EMBEDDING_API_KEY", "")
        model_id = os.getenv("EMBEDDING_MODEL_ID", "")
        model_version = os.getenv("EMBEDDING_MODEL_VERSION", "unspecified")
        return cls(endpoint, api_key, model_id, model_version)

    def embed(self, text: str) -> Sequence[float]:
        normalized_text = normalize_embedding_text(text)
        if not normalized_text:
            raise ValueError("Embedding input text cannot be empty.")

        request = Request(
            self.endpoint,
            data=json.dumps(
                {"model": self.model_id, "input": normalized_text}
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(
                f"Hosted embedding request failed with HTTP {exc.code}."
            ) from exc
        except URLError as exc:
            raise RuntimeError("Hosted embedding provider is unreachable.") from exc
        except TimeoutError as exc:
            raise RuntimeError("Hosted embedding request timed out.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Hosted embedding provider returned invalid JSON.") from exc

        try:
            vector = payload["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "Hosted embedding response did not contain an embedding vector."
            ) from exc
        if not isinstance(vector, list):
            raise RuntimeError("Hosted embedding response vector must be a list.")
        return _validated_vector(vector)


def _validated_vector(values: Sequence[float]) -> tuple[float, ...]:
    if not values:
        raise ValueError("Embedding vector cannot be empty.")
    vector = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Embedding vector values must be numeric.")
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise ValueError("Embedding vector values must be finite.")
        vector.append(numeric_value)
    return tuple(vector)


class EmbeddingService:
    def __init__(
        self,
        provider: EmbeddingProvider,
        max_cache_entries: int = 256,
        max_dimensions: int = 4096,
    ):
        if max_cache_entries < 1:
            raise ValueError("Embedding cache must allow at least one entry.")
        if max_dimensions < 1:
            raise ValueError("Embedding dimension limit must be positive.")
        self.provider = provider
        self.max_cache_entries = max_cache_entries
        self.max_dimensions = max_dimensions
        self._cache: OrderedDict[
            tuple[str, str, str], EmbeddingRecord
        ] = OrderedDict()
        self._lock = threading.RLock()

    def get_embedding(self, paper_id: str, text: str) -> EmbeddingRecord:
        if not paper_id.strip():
            raise ValueError("Paper ID cannot be empty.")
        normalized_text = normalize_embedding_text(text)
        if not normalized_text:
            raise ValueError("Embedding input text cannot be empty.")

        digest = content_hash(normalized_text)
        key = (self.provider.model_id, self.provider.model_version, digest)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return EmbeddingRecord(
                    paper_id=paper_id,
                    model_id=cached.model_id,
                    model_version=cached.model_version,
                    dimension=cached.dimension,
                    content_hash=cached.content_hash,
                    embedding=cached.embedding,
                )

            vector = _validated_vector(self.provider.embed(normalized_text))
            if len(vector) > self.max_dimensions:
                raise ValueError(
                    f"Embedding dimension exceeds limit of {self.max_dimensions}."
                )
            record = EmbeddingRecord(
                paper_id=paper_id,
                model_id=self.provider.model_id,
                model_version=self.provider.model_version,
                dimension=len(vector),
                content_hash=digest,
                embedding=vector,
            )
            self._cache[key] = record
            while len(self._cache) > self.max_cache_entries:
                self._cache.popitem(last=False)
            return record

    @property
    def cache_size(self) -> int:
        with self._lock:
            return len(self._cache)


def cosine_similarity(first: Sequence[float], second: Sequence[float]) -> float:
    first_vector = _validated_vector(first)
    second_vector = _validated_vector(second)
    if len(first_vector) != len(second_vector):
        raise ValueError("Embedding vectors must have the same dimension.")
    first_norm = math.sqrt(sum(value * value for value in first_vector))
    second_norm = math.sqrt(sum(value * value for value in second_vector))
    if first_norm == 0 or second_norm == 0:
        raise ValueError("Cosine similarity is undefined for a zero vector.")
    return sum(
        first_value * second_value
        for first_value, second_value in zip(first_vector, second_vector)
    ) / (first_norm * second_norm)


def rank_similar_papers(
    query: EmbeddingRecord,
    candidates: Sequence[EmbeddingRecord],
    threshold: float = 0.0,
    limit: int = 10,
) -> list[dict[str, float | str]]:
    if not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise ValueError("Similarity threshold must be between -1 and 1.")
    if limit < 1:
        raise ValueError("Similarity result limit must be positive.")

    matches = []
    for candidate in candidates:
        if candidate.paper_id == query.paper_id:
            continue
        if (
            candidate.model_id != query.model_id
            or candidate.model_version != query.model_version
        ):
            continue
        similarity = cosine_similarity(query.embedding, candidate.embedding)
        if similarity >= threshold:
            matches.append(
                {"paper_id": candidate.paper_id, "similarity": similarity}
            )
    return sorted(
        matches,
        key=lambda item: (-item["similarity"], item["paper_id"]),
    )[:limit]
