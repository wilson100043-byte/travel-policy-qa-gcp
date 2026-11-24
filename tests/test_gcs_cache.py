import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from app import indexer
from app.config import load_settings
from app.vertex import VERTEX_TIMEOUT_SECONDS


INDEX = {
    "schema_version": 1,
    "mode": "local",
    "embedding_model": "char-ngram-tfidf-v1",
    "idf": {},
    "chunks": [{"id": "a"}],
}


class FakeBlob:
    def __init__(self, store):
        self.store = store
        self.generation = store["generation"]

    def download_as_text(self, encoding):
        self.store["downloads"] += 1
        return json.dumps(self.store["index"])


class FakeClient:
    """Stands in for google.cloud.storage so the test makes no network call."""

    def __init__(self, store):
        self.store = store

    def bucket(self, name):
        return self

    def get_blob(self, name):
        return FakeBlob(self.store) if self.store["exists"] else None


@pytest.fixture
def gcs(monkeypatch):
    store = {"generation": 1, "index": INDEX, "exists": True, "downloads": 0}
    monkeypatch.setattr(indexer, "_gcs_client", lambda: FakeClient(store))
    monkeypatch.setattr(indexer, "_GCS_INDEX_CACHE", {})
    settings = replace(load_settings(), ai_mode="local", storage_mode="gcs", gcs_bucket="demo-bucket")
    return store, settings


def test_gcs_index_downloads_once_per_generation(gcs):
    store, settings = gcs
    indexer.load_index(settings)
    indexer.load_index(settings)
    assert store["downloads"] == 1

    store["generation"] = 2  # The Job wrote a new index.json.
    indexer.load_index(settings)
    assert store["downloads"] == 2


def test_gcs_index_missing_raises(gcs):
    store, settings = gcs
    store["exists"] = False
    with pytest.raises(FileNotFoundError):
        indexer.load_index(settings)


def test_invalid_gcs_index_is_not_cached(gcs):
    store, settings = gcs
    store["index"] = dict(INDEX, mode="vertex")
    for _ in range(2):
        with pytest.raises(ValueError):
            indexer.load_index(settings)
    assert store["downloads"] == 2


def test_vertex_calls_fit_cloud_run_timeout():
    main_tf = (Path(__file__).resolve().parent.parent / "infra" / "app" / "main.tf").read_text(encoding="utf-8")
    service = main_tf.split('resource "google_cloud_run_v2_service" "api"', 1)[1].split("\nresource ", 1)[0]
    service_timeout = int(re.search(r'timeout\s*=\s*"(\d+)s"', service).group(1))
    # Rewrite, embed and generate run one after another for a follow-up question.
    assert 3 * VERTEX_TIMEOUT_SECONDS < service_timeout


POLICY = "---\ntitle: 住宿現行\neffective_from: 2026-07-01\neffective_to:\n---\n## 上限\n每晚住宿上限 2,500 元。"


class RawBlob:
    def __init__(self, name, generation):
        self.name = name
        self.generation = generation

    def download_as_text(self, encoding):
        return POLICY


class RawClient:
    """raw/ listing whose contents can change between two list calls."""

    def __init__(self, listings):
        self.listings = listings
        self.lists = 0
        self.uploads = []

    def bucket(self, name):
        return self

    def blob(self, name):
        client = self

        class Upload:
            def upload_from_string(self, data, content_type):
                client.uploads.append(name)
        return Upload()

    def list_blobs(self, bucket, prefix):
        listing = self.listings[min(self.lists, len(self.listings) - 1)]
        self.lists += 1
        return [RawBlob(name, generation) for name, generation in listing]


def _gcs_settings():
    return replace(load_settings(), ai_mode="local", storage_mode="gcs", gcs_bucket="demo-bucket")


def test_rebuild_writes_index_when_raw_is_unchanged(monkeypatch):
    client = RawClient([[("raw/lodging.md", 1)]])
    monkeypatch.setattr(indexer, "_gcs_client", lambda: client)
    index = indexer.create_index(_gcs_settings())
    assert index is not None and client.uploads == ["processed/index.json"]


def test_stale_rebuild_does_not_overwrite_newer_index(monkeypatch):
    # A policy was replaced while this run was embedding: a newer run owns the index.
    client = RawClient([[("raw/lodging.md", 1)], [("raw/lodging.md", 2)]])
    monkeypatch.setattr(indexer, "_gcs_client", lambda: client)
    assert indexer.create_index(_gcs_settings()) is None
    assert client.uploads == []


def test_removed_policy_changes_the_snapshot(monkeypatch):
    client = RawClient([[("raw/a.md", 1), ("raw/b.md", 1)], [("raw/a.md", 1)]])
    monkeypatch.setattr(indexer, "_gcs_client", lambda: client)
    assert indexer.create_index(_gcs_settings()) is None
