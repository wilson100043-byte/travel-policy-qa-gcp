from dataclasses import replace
from datetime import date

import pytest

from app.config import load_settings
from app.documents import parse_document
from app.indexer import build_index, load_index, validate_index
from app.rag import search


def test_local_index_retrieves_current_version_only(tmp_path):
    settings = replace(load_settings(), index_path=tmp_path / "index.json", docs_dir=tmp_path)
    current = parse_document(
        "---\ntitle: 住宿現行\neffective_from: 2026-07-01\neffective_to:\n---\n"
        "## 上限\n每晚住宿上限 2,500 元。",
        "current.md",
    )
    old = parse_document(
        "---\ntitle: 住宿舊版\neffective_from: 2025-01-01\neffective_to: 2026-06-30\n---\n"
        "## 上限\n每晚住宿上限 2,000 元。",
        "old.md",
    )
    index = build_index(current + old, "local", settings)
    matches = search("住宿上限是多少", index, date(2026, 11, 22))
    assert matches
    assert all("舊版" not in item["document"] for item in matches)
    assert "2,500" in matches[0]["text"]


def test_index_mode_mismatch_is_rejected(tmp_path):
    settings = replace(load_settings(), index_path=tmp_path / "index.json")
    index = {"schema_version": 1, "mode": "vertex", "embedding_model": "gemini-embedding-001", "chunks": [{}]}
    with pytest.raises(ValueError, match="mode"):
        validate_index(index, settings)


def test_vertex_mode_requires_project(tmp_path):
    settings = replace(load_settings(), ai_mode="vertex", gcp_project="")
    chunks = parse_document(
        "---\ntitle: 測試\neffective_from: 2026-01-01\neffective_to:\n---\n## 一\n測試規定。",
        "test.md",
    )
    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        build_index(chunks, "vertex", settings)
