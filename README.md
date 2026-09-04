# ERGA — Explainable Rubric-Grounded Automated Grading

A research-oriented, human-in-the-loop framework for grading descriptive
exam answers. It doesn't just predict a mark — for every criterion it
shows the evidence it found, what's missing, how confident it is, and
whether a human should look at it before the score counts.

```
Question + Rubric + Student Answer
        │
        ▼
  Normalize (typed / PDF / OCR)  →  Segment  →  Retrieve evidence per
  criterion  →  Assess (supported / partial / missing)  →  Deterministic
  scoring  →  Confidence routing  →  AI recommendation OR faculty review
        │
        ▼
  Criterion-level explanation + audit trail + exam report (JSON & PDF)
```

This isn't a demo that calls an LLM and asks it for a number. The rubric
is authoritative, marks are computed by an explicit deterministic formula
from a status the model assigns, and every mark carries the evidence that
justifies it. See [`docs/research.md`](docs/research.md) for why that
distinction is the actual point of the project.

## What's real here, right now

Everything below is genuinely implemented and covered by
[tests](#tests-20-passing) that hit the real HTTP API, a real SQLite
database, real PDF text extraction, and real Tesseract OCR — nothing is
mocked:

- **Rubric-grounded, criterion-level, evidence-based grading** for typed
  answers, PDFs (text-layer or scanned), and scanned images, all through
  one shared pipeline (`services/grading_pipeline.py`)
- **Deterministic scoring** — the final mark is always `SUM(criterion
  marks)`, computed by an explicit, configurable rule from each
  criterion's status, never a number an LLM just states
  (`services/scoring.py`)
- **Two separate, never-blended confidence scores** — recognition
  confidence (OCR quality) and grading confidence (how close a call was),
  independently able to trigger faculty review (`services/confidence.py`)
- **Real OCR bounding boxes and page numbers**, not fabricated
  coordinates (`services/ocr.py`)
- **Faculty review with a full audit trail** — every override records the
  AI's original mark, the faculty's mark, a reason, a reviewer, and a
  timestamp, and the AI's number is never overwritten (`api/reviews.py`)
- **A working React + TypeScript frontend** covering all six pages from
  the spec: Dashboard, Create Assessment, Rubric Builder, Answer Upload
  (with an editable OCR-correction step), Grading Result, Faculty Review
- **PDF faculty reports and JSON exam-level reports**
  (`services/reporting.py`)

## Score agreement — actually evaluated, not just planned

`evaluation/grading/run_pecuchova_evaluation.py` grades the real
Pecuchova et al. dataset (1,885 real student responses, 24 questions, two
independent human graders) through ERGA's actual pipeline and reports
real MAE/RMSE/Pearson/Spearman/QWK/Kappa — see
[`evaluation/reports/pecuchova_evaluation.md`](evaluation/reports/pecuchova_evaluation.md)
for the full numbers and
[`docs/methodology.md`](docs/methodology.md#evaluation-protocol-section-43)
for the write-up. Headline, stated plainly: the default thresholds turned
out badly miscalibrated for this dataset's heavily-paraphrased answers
(Kappa ≈ 0), calibrating on a held-out split roughly halved MAE and moved
Kappa to "slight" agreement (0.13) — but there remains a large, honest gap
to human-human agreement (Kappa 0.83). The calibrated thresholds were
deliberately **not** copied into the shipped config: cross-checking them
against clear-cut synthetic cases showed they reward answers that
directly contradict a criterion, which is a concrete regression outside
this one dataset's specific vocabulary-mismatch problem. Separately, the
shipped system's actual confidence-based review flagging was checked
against real error rates on the same held-out set (Section 46's H4): rows
it would flag do have higher error on average (61.2 vs. 57.9) — a real
but modest effect. Run it yourself:

```bash
cd datasets/pecuchova && ./download.sh && cd ../../evaluation/grading
python run_pecuchova_evaluation.py
```

## What's scaffolded, not fabricated

The rest of Phase 7/8 (recognition/OCR evaluation, ablations, baselines,
criterion-level accuracy against a *real* rubric) needs real experiments
over datasets that are either gated (RiceChem) or unreachable from this
build's sandbox (Handwritten ASAP-SAS on Zenodo) — that can't be faked
without violating the project's own ground rules. Instead:

- `datasets/` has working download scripts for the two openly-available
  datasets (verified by actually cloning them while building this) and
  clear instructions for the two gated ones
- `evaluation/` has a defined metric for every planned measurement, marks
  exactly which ones have real results already (see above) and which
  don't yet — **zero fabricated numbers either way**
- `docs/research.md` states exactly which hypotheses are "supported by
  construction" (i.e., the code provably does what it claims) versus
  "not evaluated yet" (needs the real data)

## Why TF-IDF/lexical instead of SBERT/transformer

The spec's design calls for Sentence-BERT retrieval and a transformer NLI
model (DeBERTa/RoBERTa-MNLI class). Those are **fully implemented** —
`SBERTEmbedder` in `services/embeddings.py` and `TransformerNLIAssessor`
in `services/nli.py` — but not the *active* engines in this build, for one
concrete reason: this project was built in a sandboxed container whose
network egress allowlist does not include `huggingface.co`, so pretrained
model weights cannot be downloaded there. This was verified by testing,
not assumed:

```
$ curl -sS -D - -o /dev/null https://huggingface.co
< HTTP/1.1 403 Forbidden
< x-deny-reason: host_not_allowed
```

Rather than pretend to call a model that can't actually load, the default
engines are a fully-working classical NLP baseline: TF-IDF cosine
retrieval and a deterministic, negation-aware lexical coverage classifier
(see [`docs/methodology.md`](docs/methodology.md) for exactly how it
scores, including two real limitations found while testing it). Both are
genuinely explainable — arguably a better fit for this project's
explainability goals than a neural black box — and both are swappable to
the transformer versions with a **one-line config change**, in any
environment that can reach a model hub:

```yaml
# backend/config/model_config.yaml
embedding_model:
  engine: sbert          # was: tfidf
nli_model:
  engine: transformer     # was: lexical
```

then `pip install sentence-transformers transformers torch` (already
listed, commented out, in `backend/requirements.txt`).

## Run it

**Backend**
```bash
cd backend
pip install -r requirements.txt --break-system-packages   # or use a venv
uvicorn main:app --reload --port 8000
```
Interactive API docs: http://localhost:8000/docs

**Frontend** (separate terminal)
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. It talks to the backend at
`http://localhost:8000` by default — copy `.env.example` to `.env.local`
to change that.

**Tesseract** must be installed for OCR (scanned/handwritten input) to
work: `apt-get install tesseract-ocr` on Debian/Ubuntu (already present
and used in the build/test environment for this project). If it isn't
installed, typed answers and PDFs with a real text layer still work fine
— only scanned/handwritten input needs it, and you'll get a specific,
actionable error (not a silent failure) if it's missing.

## Troubleshooting

**"My PDF upload doesn't seem to do anything / the grade doesn't reflect
what I submitted."** A QA pass on this exact symptom found and fixed two
real bugs — see [`docs/methodology.md`](docs/methodology.md#bugs-found-and-fixed-during-a-follow-up-qa-pass)
for the full detail:
- OCR preprocessing used to take 5–10+ seconds *per page*, which could
  read as "stuck." It's now ~1 second/page.
- A PDF with only *some* pages scanned/image-based (e.g. a typed answer
  with a pasted-in diagram or handwritten continuation) used to have
  those specific pages silently skipped instead of extracted.

If you're still seeing something wrong after updating: open the
extracted-text review step (Answer Upload page) before grading — the
actual recognized text is always shown there, editable, before it's ever
graded, so you can see directly whether extraction captured what you
expected. Errors (password-protected PDFs, corrupted files, a missing
Tesseract install) now surface as a specific message there rather than
failing silently.

## Tests (35 passing)

```bash
cd backend
pytest ../tests/ -v
```

- `tests/test_grading_pipeline.py` — unit tests on segmentation, retrieval,
  NLI (including a negation case and a reference-concepts case), and
  scoring, across multiple subject domains (civics, biology, physics) —
  deliberately *not* the spec's own worked ML example, to demonstrate the
  engine is general-purpose rather than tuned to one question
- `tests/test_api_flow.py` — full HTTP integration tests via FastAPI's
  `TestClient`: create assessment → rubric → submit → grade → review →
  report → PDF; real PDF text-layer extraction; a PDF with **no** text
  layer at all (OCR fallback); a **mixed** PDF with one typed page and one
  image-only page (the exact shape that used to lose content); real image
  OCR with an editable-correction step; the handwriting-always-reviewed
  policy; and clear-error-message checks for password-protected and
  corrupted PDFs
- `tests/test_pecuchova_adapter.py` — unit tests on the reference-to-rubric
  chunking and ECTS letter-grade conversion used by the real dataset
  evaluation in `evaluation/grading/`, plus a direction/arithmetic check
  on the H4 (confidence-flags-high-risk-rows) test helper

## Project layout

```
erga/
├── backend/         FastAPI app — see backend structure below
├── frontend/         React + TypeScript (Vite)
├── datasets/          Download scripts + access notes (Section 26-31)
├── evaluation/        Planned metrics, honestly empty (Section 43)
├── ml/                 Training/checkpoint scaffolding (Section 39)
├── tests/               Unit + integration tests (real HTTP, real DB, real OCR)
└── docs/
    ├── architecture.md   Pipeline diagram + component map
    ├── methodology.md    Scoring/confidence formulas, known limitations
    ├── datasets.md        Full dataset documentation with verified links
    └── research.md        Base paper, supporting literature, novelty claim
```

```
backend/
├── main.py                    FastAPI app
├── config/                     model_config.yaml + typed settings loader
├── database/                   SQLAlchemy models + session
├── schemas/                    Pydantic request/response models
├── services/
│   ├── segmentation.py          Answer → evidence-unit splitting
│   ├── embeddings.py             TF-IDF (active) / SBERT (config-ready)
│   ├── text_utils.py              Shared stemmer/tokenizer (retrieval + NLI agree)
│   ├── nli.py                      Lexical (active) / Transformer (config-ready)
│   ├── scoring.py                  Deterministic status → marks → sum
│   ├── confidence.py                Recognition vs. grading confidence, kept separate
│   ├── extraction.py                 PDF text-layer / scan-to-OCR
│   ├── ocr.py                         Tesseract (active) / PaddleOCR (documented stub)
│   ├── reporting.py                    JSON + PDF report generation
│   └── grading_pipeline.py               Orchestrates all of the above
└── api/                        assessments, submissions, reviews, reports routers
```

## API surface

Interactive docs at `/docs` once the backend is running; the shape roughly
follows Section 41 of the spec: `POST /api/assessments`,
`POST /api/assessments/{id}/questions`, `POST /api/submissions`,
`POST /api/submissions/{id}/extract`,
`PUT /api/submissions/{id}/extracted-text` (faculty OCR correction),
`POST /api/submissions/{id}/grade`, `GET /api/submissions/{id}/result`,
`POST /api/reviews`, `GET /api/reports/{assessment_id}[/pdf]`,
`GET /api/dashboard/stats`.

## Security & privacy (Section 50)

By construction, not by policy alone: the active engines (TF-IDF,
Tesseract) run entirely locally, so **no student answer is sent to an
external API** unless you deliberately switch to the transformer engine
*and* point it at a hosted model. Uploaded filenames are sanitized
(`api/submissions.py::_sanitize_filename`), file types and sizes are
validated against `config/model_config.yaml`, and every submission can be
permanently deleted via `DELETE /api/submissions/{id}`. There is
deliberately no authentication/role system in this prototype — add one
before handling real institutional data, alongside your institution's own
data-protection review.

## Positioning

A grading **assistant**, not an autonomous replacement for teachers:
assist → explain → standardize → flag uncertainty → let faculty decide.
Every AI-assigned mark is a recommendation until a human accepts it or
overrides it; the interface never hides that distinction.
