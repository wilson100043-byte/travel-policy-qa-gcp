import io
import json
from dataclasses import replace
from urllib.error import HTTPError

import pytest

from app import vertex
from app.config import load_settings
from app.vertex import EMBEDDING_DIMENSIONS, VertexClient, VertexUnavailable


@pytest.fixture
def client(monkeypatch):
    settings = replace(load_settings(), ai_mode="vertex", gcp_project="demo-project", vertex_location="asia-east1")
    instance = VertexClient(settings)
    # No real credentials: the token lookup is replaced for every test.
    monkeypatch.setattr(instance, "_token", lambda: "test-token")
    return instance


def fake_urlopen(monkeypatch, reply, calls):
    def _open(request, timeout):
        calls.append({
            "url": request.full_url,
            "auth": request.get_header("Authorization"),
            "body": json.loads(request.data.decode("utf-8")),
            "timeout": timeout,
        })
        return io.BytesIO(json.dumps(reply).encode("utf-8"))
    monkeypatch.setattr(vertex, "urlopen", _open)


def test_embed_calls_regional_predict_endpoint(client, monkeypatch):
    calls = []
    fake_urlopen(monkeypatch, {"predictions": [{"embeddings": {"values": [0.1, 0.2]}}]}, calls)

    assert client.embed("住宿上限", "RETRIEVAL_DOCUMENT", title="住宿規定") == [0.1, 0.2]
    call = calls[0]
    assert call["url"] == (
        "https://asia-east1-aiplatform.googleapis.com/v1/projects/demo-project/locations/asia-east1"
        "/publishers/google/models/gemini-embedding-001:predict"
    )
    assert call["auth"] == "Bearer test-token"
    assert call["body"]["instances"] == [{"content": "住宿上限", "task_type": "RETRIEVAL_DOCUMENT", "title": "住宿規定"}]
    assert call["body"]["parameters"]["outputDimensionality"] == EMBEDDING_DIMENSIONS
    assert call["timeout"] == vertex.VERTEX_TIMEOUT_SECONDS


def test_query_embedding_omits_title(client, monkeypatch):
    calls = []
    fake_urlopen(monkeypatch, {"predictions": [{"embeddings": {"values": [1.0]}}]}, calls)
    client.embed("住宿上限", "RETRIEVAL_QUERY", title="ignored")
    assert "title" not in calls[0]["body"]["instances"][0]


def test_generate_reads_candidate_text(client, monkeypatch):
    calls = []
    reply = {"candidates": [{"content": {"parts": [{"text": "每晚上限 2,500 元。"}]}}]}
    fake_urlopen(monkeypatch, reply, calls)

    assert client.generate("問題") == "每晚上限 2,500 元。"
    assert calls[0]["url"].endswith("/models/gemini-2.5-flash-lite:generateContent")
    assert calls[0]["body"]["generationConfig"]["temperature"] == 0.1


def test_rate_limit_becomes_user_message(client, monkeypatch):
    def _open(request, timeout):
        raise HTTPError(request.full_url, 429, "Too Many Requests", {}, None)
    monkeypatch.setattr(vertex, "urlopen", _open)

    with pytest.raises(VertexUnavailable, match="請求過多"):
        client.generate("問題")


def test_global_location_uses_global_host(monkeypatch):
    settings = replace(load_settings(), ai_mode="vertex", gcp_project="demo-project", vertex_location="global")
    url = VertexClient(settings)._url("gemini-2.5-flash-lite", "generateContent")
    assert url.startswith("https://aiplatform.googleapis.com/v1/projects/demo-project/locations/global/")
