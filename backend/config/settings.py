"""
Typed access to model_config.yaml, with environment-variable overrides for
deployment-specific values (database URL, upload directory).

Rule 4 (spec Section 52): "Make every model configurable." This module is
the single place that decides which embedding engine, which NLI engine,
which thresholds, and which OCR engine are active. Nothing downstream
hard-codes a model name.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(
    os.environ.get("ERGA_CONFIG_PATH", Path(__file__).parent / "model_config.yaml")
)
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _load_raw() -> dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass
class EmbeddingConfig:
    engine: str
    tfidf: dict[str, Any]
    sbert: dict[str, Any]


@dataclass
class NLIConfig:
    engine: str
    lexical: dict[str, Any]
    transformer: dict[str, Any]


@dataclass
class RetrievalConfig:
    top_k: int
    min_similarity: float


@dataclass
class ThresholdsConfig:
    nli_supported_min: float
    nli_partial_min: float
    recognition_review_below: float
    grading_review_below: float


@dataclass
class ScoringConfig:
    mode: str
    fixed_fractions: dict[str, float]
    round_ndigits: int


@dataclass
class OCRConfig:
    engine: str
    handwriting_force_review: bool
    tesseract_psm: int
    tesseract_lang: str
    denoise_method: str


@dataclass
class StorageConfig:
    upload_dir: Path
    max_upload_mb: int
    allowed_extensions: list[str]


@dataclass
class Config:
    embedding: EmbeddingConfig
    nli: NLIConfig
    retrieval: RetrievalConfig
    thresholds: ThresholdsConfig
    scoring: ScoringConfig
    ocr: OCRConfig
    storage: StorageConfig
    database_url: str
    min_segment_chars: int
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def load_config() -> Config:
    raw = _load_raw()

    storage_raw = raw["storage"]
    upload_dir = BACKEND_ROOT / storage_raw["upload_dir"]
    upload_dir.mkdir(parents=True, exist_ok=True)

    database_url = os.environ.get("DATABASE_URL", raw["database"]["url"])

    return Config(
        embedding=EmbeddingConfig(
            engine=raw["embedding_model"]["engine"],
            tfidf=raw["embedding_model"]["tfidf"],
            sbert=raw["embedding_model"]["sbert"],
        ),
        nli=NLIConfig(
            engine=raw["nli_model"]["engine"],
            lexical=raw["nli_model"]["lexical"],
            transformer=raw["nli_model"]["transformer"],
        ),
        retrieval=RetrievalConfig(
            top_k=raw["retrieval"]["top_k"],
            min_similarity=raw["retrieval"]["min_similarity"],
        ),
        thresholds=ThresholdsConfig(
            nli_supported_min=raw["thresholds"]["nli"]["supported_min"],
            nli_partial_min=raw["thresholds"]["nli"]["partial_min"],
            recognition_review_below=raw["thresholds"]["confidence"]["recognition_review_below"],
            grading_review_below=raw["thresholds"]["confidence"]["grading_review_below"],
        ),
        scoring=ScoringConfig(
            mode=raw["scoring"]["mode"],
            fixed_fractions=raw["scoring"]["fixed_fractions"],
            round_ndigits=raw["scoring"]["round_ndigits"],
        ),
        ocr=OCRConfig(
            engine=raw["ocr"]["engine"],
            handwriting_force_review=raw["ocr"]["handwriting_force_review"],
            tesseract_psm=raw["ocr"]["tesseract_psm"],
            tesseract_lang=raw["ocr"]["tesseract_lang"],
            denoise_method=raw["ocr"]["denoise_method"],
        ),
        storage=StorageConfig(
            upload_dir=upload_dir,
            max_upload_mb=storage_raw["max_upload_mb"],
            allowed_extensions=storage_raw["allowed_extensions"],
        ),
        database_url=database_url,
        min_segment_chars=raw["segmentation"]["min_segment_chars"],
        raw=raw,
    )


# Module-level singleton, imported by services/api layers.
config = load_config()
