"""Create and load a small JSON vector index from Markdown policies.

Local use: python -m app.indexer
Cloud Run Job: STORAGE_MODE=gcs AI_MODE=gemini ... python -m app.indexer
"""

import json
import math
import re
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List

from app.config import Settings, load_settings, require_gemini_opt_in
from app.documents import Chunk, fingerprint_documents, load_local_documents, parse_document
from app.gemini import GeminiClient


SCHEMA_VERSION = 1
TOKEN = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+")


def grams(text: str) -> Counter:
    """Character bigrams/trigrams suit short Chinese questions without a tokenizer."""
    normalized = "".join(TOKEN.findall(text.lower()))
    result = Counter()
    for length in (2, 3):
        result.update(normalized[i : i + length] for i in range(max(0, len(normalized) - length + 1)))
    return result


def _normalized_tfidf(counts: Counter, idf: Dict[str, float]) -> dict:
    weighted = {term: (1 + math.log(count)) * idf[term] for term, count in counts.items() if term in idf}
    norm = math.sqrt(sum(value * value for value in weighted.values()))
    return {term: value / norm for term, value in weighted.items()} if norm else {}


def vectorize_query(question: str, index: dict) -> dict:
    return _normalized_tfidf(grams(question), index["idf"])


def build_index(chunks: List[Chunk], mode: str, settings: Settings, fingerprint: str = "") -> dict:
    if not chunks:
        raise ValueError("no policy sections to index")
    result = {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "embedding_model": settings.gemini_embedding_model if mode == "gemini" else "char-ngram-tfidf-v1",
        "source_fingerprint": fingerprint,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "chunks": [],
    }
    if mode == "local":
        counts = [grams((chunk.document + " " + chunk.section + " ") * 3 + chunk.text) for chunk in chunks]
        document_frequency = Counter(term for count in counts for term in count)
        result["idf"] = {
            term: math.log((1 + len(chunks)) / (1 + frequency)) + 1
            for term, frequency in document_frequency.items()
        }
        vectors = [_normalized_tfidf(count, result["idf"]) for count in counts]
    elif mode == "gemini":
        client = GeminiClient(settings)  # Enforces all opt-in gates before first call.
        vectors = [
            client.embed(chunk.document + "\n" + chunk.section + "\n" + chunk.text,
                         "RETRIEVAL_DOCUMENT", title=chunk.document + " - " + chunk.section)
            for chunk in chunks
        ]
    else:
        raise ValueError("unsupported index mode")
    result["chunks"] = [dict(asdict(chunk), vector=vector) for chunk, vector in zip(chunks, vectors)]
    return result


def _gcs_client():
    try:
        from google.cloud import storage
    except ImportError:
        raise RuntimeError("google-cloud-storage is required for STORAGE_MODE=gcs") from None
    return storage.Client()


def _require_bucket(settings: Settings) -> str:
    if not settings.gcs_bucket:
        raise ValueError("GCS_BUCKET is required for STORAGE_MODE=gcs")
    return settings.gcs_bucket


def read_source_chunks(settings: Settings) -> List[Chunk]:
    if settings.storage_mode == "local":
        return load_local_documents(settings.docs_dir)
    client = _gcs_client()
    bucket = client.bucket(_require_bucket(settings))
    blobs = sorted(
        (blob for blob in client.list_blobs(bucket, prefix=settings.gcs_raw_prefix) if blob.name.endswith(".md")),
        key=lambda blob: blob.name,
    )
    if not blobs:
        raise FileNotFoundError("no Markdown files in GCS raw prefix")
    chunks = []
    for blob in blobs:
        chunks.extend(parse_document(blob.download_as_text(encoding="utf-8"), Path(blob.name).name))
    return chunks


def save_index(index: dict, settings: Settings) -> None:
    encoded = json.dumps(index, ensure_ascii=False, separators=(",", ":"))
    if settings.storage_mode == "local":
        settings.index_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = settings.index_path.with_suffix(".tmp")
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(settings.index_path)
    else:
        _gcs_client().bucket(_require_bucket(settings)).blob(settings.gcs_processed_object).upload_from_string(
            encoded, content_type="application/json"
        )


def load_index(settings: Settings) -> dict:
    if settings.storage_mode == "local":
        if not settings.index_path.exists():
            if settings.ai_mode == "gemini":
                raise FileNotFoundError("Gemini index missing; run python -m app.indexer explicitly")
            return create_index(settings)
        index = json.loads(settings.index_path.read_text(encoding="utf-8"))
        fingerprint = fingerprint_documents(settings.docs_dir)
        if fingerprint and index.get("source_fingerprint") != fingerprint:
            if settings.ai_mode == "gemini":
                raise ValueError("policy documents changed; rebuild Gemini index explicitly")
            return create_index(settings)
    else:
        index = _load_gcs_index(settings)
    validate_index(index, settings)
    return index


# (bucket, object) -> (generation, parsed index). One process serves many
# questions, so download index.json only when the Job has written a new version.
_GCS_INDEX_CACHE: Dict[tuple, tuple] = {}


def _load_gcs_index(settings: Settings) -> dict:
    bucket = _require_bucket(settings)
    # get_blob is a single metadata request; it returns None when the object is missing.
    blob = _gcs_client().bucket(bucket).get_blob(settings.gcs_processed_object)
    if blob is None:
        raise FileNotFoundError("GCS processed index missing; run Cloud Run Job")
    key = (bucket, settings.gcs_processed_object)
    cached = _GCS_INDEX_CACHE.get(key)
    if cached and cached[0] == blob.generation:
        return cached[1]
    # The blob carries its generation, so this download matches the version checked above.
    index = json.loads(blob.download_as_text(encoding="utf-8"))
    validate_index(index, settings)
    _GCS_INDEX_CACHE[key] = (blob.generation, index)
    return index


def validate_index(index: dict, settings: Settings) -> None:
    if index.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("index format unsupported; rebuild index")
    if index.get("mode") != settings.ai_mode:
        raise ValueError("index mode does not match AI_MODE; rebuild index")
    expected = settings.gemini_embedding_model if settings.ai_mode == "gemini" else "char-ngram-tfidf-v1"
    if index.get("embedding_model") != expected:
        raise ValueError("index embedding model changed; rebuild index")
    if not isinstance(index.get("chunks"), list) or not index["chunks"]:
        raise ValueError("index has no sections")
    if settings.ai_mode == "local" and not isinstance(index.get("idf"), dict):
        raise ValueError("local index is missing IDF data")


def create_index(settings: Settings = None) -> dict:
    settings = settings or load_settings()
    if settings.ai_mode == "gemini":
        require_gemini_opt_in(settings)
    chunks = read_source_chunks(settings)
    fingerprint = (fingerprint_documents(settings.docs_dir) or "") if settings.storage_mode == "local" else ""
    index = build_index(chunks, settings.ai_mode, settings, fingerprint)
    save_index(index, settings)
    return index


if __name__ == "__main__":
    index = create_index()
    print("Indexed {} sections in {} mode.".format(len(index["chunks"]), index["mode"]))
