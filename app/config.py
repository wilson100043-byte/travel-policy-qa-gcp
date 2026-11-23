"""Runtime configuration. Importing this module never starts a network call."""

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    ai_mode: str
    storage_mode: str
    docs_dir: Path
    index_path: Path
    web_dir: Path
    gcs_bucket: str
    gcs_raw_prefix: str
    gcs_processed_object: str
    gcp_project: str
    vertex_location: str
    vertex_embedding_location: str
    generation_model: str
    embedding_model: str


def load_settings() -> Settings:
    # Local runs default to offline so tests and reviewers need no cloud account.
    # The Cloud Run deployment sets AI_MODE=vertex explicitly.
    ai_mode = os.getenv("AI_MODE", "local").strip().lower()
    if ai_mode == "offline":
        ai_mode = "local"
    if ai_mode not in {"local", "vertex"}:
        raise ValueError("AI_MODE must be local or vertex")
    storage_mode = os.getenv("STORAGE_MODE", "local").strip().lower()
    if storage_mode not in {"local", "gcs"}:
        raise ValueError("STORAGE_MODE must be local or gcs")
    return Settings(
        ai_mode=ai_mode,
        storage_mode=storage_mode,
        docs_dir=Path(os.getenv("POLICY_DOCS_DIR", str(ROOT / "policy_docs"))),
        index_path=Path(os.getenv("INDEX_PATH", str(ROOT / "data" / "processed" / "index.json"))),
        web_dir=Path(os.getenv("WEB_DIR", str(ROOT / "web"))),
        gcs_bucket=os.getenv("GCS_BUCKET", "").strip(),
        gcs_raw_prefix=os.getenv("GCS_RAW_PREFIX", "raw/").strip("/") + "/",
        gcs_processed_object=os.getenv("GCS_PROCESSED_OBJECT", "processed/index.json").strip("/"),
        gcp_project=os.getenv("GOOGLE_CLOUD_PROJECT", "").strip(),
        # Model availability was confirmed for these locations in Google's docs:
        # gemini-3.5-flash-lite on the "us" multi-region, gemini-embedding-001 on us-central1.
        vertex_location=os.getenv("VERTEX_LOCATION", "us").strip(),
        vertex_embedding_location=os.getenv("VERTEX_EMBEDDING_LOCATION", "us-central1").strip(),
        generation_model=os.getenv("VERTEX_GENERATION_MODEL", "gemini-3.5-flash-lite"),
        embedding_model=os.getenv("VERTEX_EMBEDDING_MODEL", "gemini-embedding-001"),
    )


def require_vertex(settings: Settings) -> None:
    if settings.ai_mode != "vertex":
        raise ValueError("Vertex AI calls require AI_MODE=vertex")
    if not settings.gcp_project:
        raise ValueError("Vertex AI mode needs GOOGLE_CLOUD_PROJECT")
    if not settings.vertex_location or not settings.vertex_embedding_location:
        raise ValueError("Vertex AI mode needs VERTEX_LOCATION and VERTEX_EMBEDDING_LOCATION")
