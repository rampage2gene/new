"""Application settings.

Every tunable lives here so individual pipeline stages stay free of
environment lookups. Values come from environment variables or a `.env`
file in the backend directory.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MDI_", env_file=BACKEND_DIR / ".env", extra="ignore")

    # Storage layout. Originals, page renders and the database are kept apart so
    # any one of them can be moved to a different backend later.
    data_dir: Path = REPO_DIR / "data"
    database_url: str | None = None

    # Rendering / OCR
    render_dpi: int = 150
    ocr_dpi: int = 300
    ocr_engine: str = "auto"  # auto (RapidOCR + Tesseract, both read every scanned page) | rapid | tesseract | none
    ocr_languages: str = "eng"
    ocr_retry_below: float = 0.80  # Tesseract re-reads a binarised page when its mean word confidence is below this
    min_embedded_chars_per_page: int = 40  # below this a page is treated as a scan
    # RapidOCR runs native code (onnxruntime). In its own process a crash costs
    # one page's second reading; in the server process it would end the app.
    ocr_isolate: bool = True
    ocr_page_timeout: float = 180.0  # a page the reader has not answered in this long is given up
    ocr_start_timeout: float = 120.0  # loading the models on a slow disk can take a while
    ocr_max_stops_per_document: int = 3  # after this many stops the reader sits out the rest of the document
    ocr_crash_once: bool = False  # test hook: the first reader started crashes on its first page

    # Quality control
    low_confidence_threshold: float = 0.80
    # Verification: every value read from a scan is checked against the second
    # reader; a value the readers disagree on is left blank to fill in.
    verify: bool = True
    verify_ai: bool = True  # only has an effect when an Anthropic key is configured
    ai_verify_max_pages: int = 60

    # Write <data_dir>/exports/<name>/ (OCR'd PDF, clean PDF, workbook, CSV, JSON, text)
    # for every processed document and again after each edit.
    auto_export: bool = True

    # AI layer
    anthropic_api_key: str | None = None
    ai_model: str = "claude-opus-5"
    ai_max_tokens: int = 8000
    ai_effort: str = "medium"
    ai_enabled: bool = True
    # Optional hosted embedding provider (Voyage AI). Local TF-IDF is used when unset.
    voyage_api_key: str | None = None
    voyage_model: str = "voyage-3-lite"

    # Retrieval
    search_top_k: int = 12

    # Processing: run the pipeline in worker threads (False = inline, used by tests)
    background_processing: bool = True
    ingest_workers: int = 2
    # Watch <data_dir>/inbox for dropped files (False in tests, which call scan_once())
    inbox_watcher: bool = True

    # Serving
    frontend_dist: Path = REPO_DIR / "frontend" / "dist"
    max_upload_mb: int = 200
    # Phone access: the desktop app serves the UI on the local network so a phone
    # on the same Wi-Fi can open it, and gates the API with a pairing key that
    # the launcher generates. With no key configured (dev server, Docker) the
    # API is open, as it was before.
    lan: bool = True
    access_key: str | None = None

    @property
    def originals_dir(self) -> Path:
        return self.data_dir / "originals"

    @property
    def pages_dir(self) -> Path:
        return self.data_dir / "pages"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "index.db"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.originals_dir, self.pages_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
