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
    gemini_api_key: str
    free_tier_confirmed: bool
    gemini_generation_model: str
    gemini_embedding_model: str


def load_settings() -> Settings:
    ai_mode = os.getenv("AI_MODE", "local").strip().lower()
    if ai_mode == "offline":
        ai_mode = "local"
    if ai_mode not in {"local", "gemini"}:
        raise ValueError("AI_MODE must be local or gemini")
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
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        free_tier_confirmed=os.getenv("GEMINI_FREE_TIER_CONFIRMED", "").strip().lower() in {"1", "true", "yes"},
        gemini_generation_model=os.getenv("GEMINI_GENERATION_MODEL", "gemini-3.1-flash-lite"),
        gemini_embedding_model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
    )


def require_gemini_opt_in(settings: Settings) -> None:
    if settings.ai_mode != "gemini":
        raise ValueError("Gemini calls require AI_MODE=gemini")
    if not settings.gemini_api_key:
        raise ValueError("Gemini mode needs GEMINI_API_KEY")
    if not settings.free_tier_confirmed:
        raise ValueError("Gemini mode needs GEMINI_FREE_TIER_CONFIRMED=1 after checking account billing status")
