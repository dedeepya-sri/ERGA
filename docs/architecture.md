# Architecture

## Pipeline

```
 QUESTION + RUBRIC                     Student Answer
        │                                    │
        │                  ┌─────────────────┼─────────────────┐
        │                  ▼                 ▼                 ▼
        │                Typed              PDF          Scan / Handwriting
        │                  │                 │                 │
        │                  │        text layer? ──no──►   OCR (Tesseract)
        │                  │        │yes                       │
        │                  │        ▼                          │
        │                  └──────► Normalized Lines ◄──────────┘
        │                                    │            (page + real bbox
        │                                    │             where OCR-derived)
        │                                    ▼
        │                       Answer Segmentation
        │                        (services/segmentation.py)
        │                                    │
        │                                    ▼
        └───────────────────────► Rubric ↔ Evidence Retrieval
                                    (services/embeddings.py — TF-IDF cosine,
                                     SBERT-ready)
                                                │
                                                ▼
                                    Semantic Assessment (NLI)
                                    (services/nli.py — lexical coverage +
                                     negation check, transformer-ready)
                                                │
                                ┌───────────────┼───────────────┐
                                ▼                ▼                ▼
                            Supported        Partial           Missing
                                │                │                │
                                └───────────────┼───────────────┘
                                                ▼
                                Deterministic Rubric Scoring
                                (services/scoring.py — status → marks,
                                 SUM(criteria) → final, no hidden adjustment)
                                                │
                                ┌───────────────┴────────────────┐
                                ▼                                 ▼
                    Recognition Confidence               Grading Confidence
                    (extraction/OCR — real,               (NLI margin — never
                     never fabricated)                     blended with the left)
                                └───────────────┬────────────────┘
                                                ▼
                                  Confidence Decision
                                  (services/confidence.py)
                                    │                  │
                                  HIGH                LOW
                                    │                  │
                                    ▼                  ▼
                            AI recommendation    Faculty review (api/reviews.py,
                                    │              audit trail in Review table)
                                    └────────┬─────────┘
                                             ▼
                                Final Examination Report
                                (services/reporting.py — JSON + PDF)
```

## Component map

| Concern | Module | Notes |
|---|---|---|
| Config / model selection | `config/settings.py`, `config/model_config.yaml` | Single source of truth for which engines and thresholds are active |
| Database schema | `database/models.py` | SQLAlchemy ORM; SQLite by default, swap via `DATABASE_URL` |
| API schemas | `schemas/schemas.py` | Pydantic request/response models |
| Segmentation | `services/segmentation.py` | Rule-based sentence/line splitter — no downloaded tokenizer needed |
| Retrieval | `services/embeddings.py` | `TfidfEmbedder` (active) / `SBERTEmbedder` (ready, needs model hub access) |
| Shared tokenization | `services/text_utils.py` | One stemmer/stopword list shared by retrieval *and* NLI, so they can't disagree on word forms |
| Semantic assessment | `services/nli.py` | `LexicalNLIAssessor` (active) / `TransformerNLIAssessor` (ready) |
| Scoring | `services/scoring.py` | Status → marks mapping; the only place a status becomes a number |
| Confidence routing | `services/confidence.py` | Recognition vs. grading confidence, kept separate |
| PDF/image extraction | `services/extraction.py` | Text-layer detection, page-to-image rendering, preprocessing |
| OCR | `services/ocr.py` | `TesseractOCREngine` (active) / `PaddleOCREngine` (stub, documented) |
| Reporting | `services/reporting.py` | JSON aggregate report + reportlab PDF |
| Orchestration | `services/grading_pipeline.py` | The one function that runs a submission through the whole pipeline and persists it |
| HTTP API | `api/*.py` | FastAPI routers, one per resource group |
| Frontend | `frontend/src/pages/*.tsx` | React + TypeScript, six pages matching Section 21 |

## Why services are split this way

Every stage that has a genuine "which model?" question (embedding, NLI,
OCR) is implemented as an abstract interface with exactly one active,
fully-working implementation and at least one documented, code-complete
alternative gated behind a config flag. That mirrors Section 52 Rule 4
("make every model configurable") literally rather than in spirit only —
`model_config.yaml` is the only file you should need to touch to change
which engine runs.

## Request lifecycle for one submission

1. `POST /api/submissions` — creates a `Submission` row; typed input also
   creates its `ExtractedAnswer` immediately (nothing to recognize).
2. `POST /api/submissions/{id}/extract` — for PDF/scan/handwritten only;
   runs `services/extraction.py`, stores text + real recognition
   confidence + (when available) per-line page/bbox.
3. `PUT /api/submissions/{id}/extracted-text` — optional faculty
   correction; flips `manually_corrected` and sets recognition confidence
   to 1.0 (a human has now verified it).
4. `POST /api/submissions/{id}/grade` — runs
   `services/grading_pipeline.grade_submission()`, replacing any prior
   `CriterionResult`/`Evidence` rows for that submission (idempotent
   re-grading).
5. `GET /api/submissions/{id}/result` — assembles the stored result plus
   live-computed review routing (`services/confidence.py`) into the
   response the Grading Result and Faculty Review pages render.
6. `POST /api/reviews` — writes a `Review` row linked to one
   `CriterionResult`; the AI's original marks are preserved alongside the
   faculty's, never overwritten.
7. `GET /api/reports/{assessment_id}[/pdf]` — aggregates across every
   question/submission in an assessment (Section 19).
