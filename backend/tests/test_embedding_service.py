import json
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.embedding_service import (
    EmbeddingRecord,
    EmbeddingService,
    HostedEmbeddingProvider,
    content_hash,
    cosine_similarity,
    normalize_embedding_text,
    rank_similar_papers,
)


class FakeProvider:
    model_id = "test-model"
    model_version = "v1"

    def __init__(self):
        self.calls = []

    def embed(self, text):
        self.calls.append(text)
        return [1.0, 0.0]


def test_content_hash_normalizes_unicode_and_whitespace():
    assert normalize_embedding_text("  A\u212b   paper \n text ") == "AÅ paper text"
    assert content_hash(" A\u212b  paper text ") == content_hash("AÅ paper\ntext")


def test_embedding_cache_reuses_content_and_changes_for_text_or_model_version():
    provider = FakeProvider()
    service = EmbeddingService(provider)

    first = service.get_embedding("paper-a", "A paper   about research.")
    same_content_other_paper = service.get_embedding(
        "paper-b", "A paper about research."
    )
    assert len(provider.calls) == 1
    assert first.paper_id == "paper-a"
    assert same_content_other_paper.paper_id == "paper-b"
    assert first.embedding == same_content_other_paper.embedding
    assert first.dimension == 2
    assert first.content_hash == content_hash("A paper about research.")

    service.get_embedding("paper-a", "Changed source content.")
    provider.model_version = "v2"
    service.get_embedding("paper-a", "Changed source content.")
    assert len(provider.calls) == 3
    assert service.cache_size == 3


def test_embedding_cache_is_bounded_and_evicts_least_recently_used():
    provider = FakeProvider()
    service = EmbeddingService(provider, max_cache_entries=2)

    service.get_embedding("paper-a", "first text")
    service.get_embedding("paper-b", "second text")
    service.get_embedding("paper-a", "first text")
    service.get_embedding("paper-c", "third text")
    service.get_embedding("paper-b", "second text")

    assert service.cache_size == 2
    assert len(provider.calls) == 4


def test_empty_ids_text_and_oversized_vectors_fail_explicitly():
    service = EmbeddingService(FakeProvider(), max_dimensions=1)
    with pytest.raises(ValueError, match="Paper ID cannot be empty"):
        service.get_embedding(" ", "paper content")
    with pytest.raises(ValueError, match="text cannot be empty"):
        service.get_embedding("paper-a", "  \n ")
    with pytest.raises(ValueError, match="dimension exceeds limit"):
        service.get_embedding("paper-a", "paper content")
    assert service.cache_size == 0


def test_hosted_provider_sends_server_side_auth_and_parses_vector():
    provider = HostedEmbeddingProvider(
        endpoint="https://embeddings.example/v1/embeddings",
        api_key="test-secret",
        model_id="configured-model",
        model_version="2026-01",
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"data": [{"embedding": [0.25, 0.75]}]}).encode()

    with patch(
        "app.services.embedding_service.urlopen", return_value=Response()
    ) as mock_urlopen:
        service = EmbeddingService(provider)
        record = service.get_embedding("paper-a", "  Example   input ")

    request = mock_urlopen.call_args.args[0]
    assert json.loads(request.data) == {
        "model": "configured-model",
        "input": "Example input",
    }
    assert request.get_header("Authorization") == "Bearer test-secret"
    assert record.model_id == "configured-model"
    assert record.model_version == "2026-01"
    assert record.embedding == (0.25, 0.75)


def test_hosted_provider_does_not_expose_error_body_or_api_key():
    provider = HostedEmbeddingProvider(
        endpoint="https://embeddings.example/v1/embeddings",
        api_key="test-secret",
        model_id="configured-model",
    )
    error = HTTPError(
        provider.endpoint,
        401,
        "unauthorized",
        hdrs=None,
        fp=None,
    )

    with patch(
        "app.services.embedding_service.urlopen", side_effect=error
    ), pytest.raises(RuntimeError, match="HTTP 401") as caught:
        provider.embed("text")

    assert "test-secret" not in str(caught.value)


@pytest.mark.parametrize(
    ("response_body", "message"),
    [
        (b"not-json", "invalid JSON"),
        (b'{"data": []}', "did not contain an embedding vector"),
        (b'{"data": [{"embedding": []}]}', "vector cannot be empty"),
        (b'{"data": [{"embedding": [NaN]}]}', "must be finite"),
    ],
)
def test_hosted_provider_rejects_invalid_responses(response_body, message):
    provider = HostedEmbeddingProvider(
        endpoint="https://embeddings.example/v1/embeddings",
        api_key="test-secret",
        model_id="configured-model",
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return response_body

    with patch(
        "app.services.embedding_service.urlopen", return_value=Response()
    ), pytest.raises((RuntimeError, ValueError), match=message):
        provider.embed("text")


def test_hosted_provider_reports_timeout_without_configuration_details():
    provider = HostedEmbeddingProvider(
        endpoint="https://embeddings.example/v1/embeddings",
        api_key="test-secret",
        model_id="configured-model",
    )

    with patch(
        "app.services.embedding_service.urlopen", side_effect=TimeoutError
    ), pytest.raises(RuntimeError, match="timed out") as caught:
        provider.embed("text")

    assert "test-secret" not in str(caught.value)


def test_similarity_ranking_filters_threshold_model_and_self():
    query = EmbeddingRecord(
        "paper-query", "model", "v1", 2, "query", (1.0, 0.0)
    )
    candidates = [
        EmbeddingRecord("paper-low", "model", "v1", 2, "low", (0.0, 1.0)),
        EmbeddingRecord("paper-high", "model", "v1", 2, "high", (0.8, 0.6)),
        EmbeddingRecord("paper-query", "model", "v1", 2, "self", (1.0, 0.0)),
        EmbeddingRecord("paper-other", "model", "v2", 2, "other", (1.0, 0.0)),
    ]

    result = rank_similar_papers(query, candidates, threshold=0.5)

    assert result == [{"paper_id": "paper-high", "similarity": pytest.approx(0.8)}]
    assert cosine_similarity((1, 0), (0, 1)) == pytest.approx(0)
    with pytest.raises(ValueError, match="same dimension"):
        cosine_similarity((1,), (1, 2))
    with pytest.raises(ValueError, match="zero vector"):
        cosine_similarity((0, 0), (1, 0))
    with pytest.raises(ValueError, match="threshold"):
        rank_similar_papers(query, candidates, threshold=2)
