# evaluation/

System-level evaluation against the datasets in `docs/datasets.md`, per
the protocol in `docs/methodology.md`.

| Subfolder | Status | What it covers |
|---|---|---|
| `grading/` | **Run** — `run_pecuchova_evaluation.py`, real results in `reports/` | MAE/RMSE/Pearson/Spearman/QWK/Kappa of final scores against Dataset B (Pecuchova et al.)'s two human graders, before and after threshold calibration |
| `recognition/` | Not run | Character Error Rate, Word Error Rate for the OCR/HTR pipeline — depends on Dataset C (Handwritten ASAP-SAS), not downloadable from this build's sandbox (see `docs/datasets.md`) |
| `evidence/` | Not run | Evidence precision/recall, criterion-evidence relevance, unsupported-evidence rate — requires evidence-relevance annotations this project does not yet have; see `docs/methodology.md` |
| `reports/` | Partially populated | `pecuchova_evaluation.md` + `_raw.csv` are real, generated output. Nothing else is there yet. |

Also not yet run, even within `grading/`: criterion-level status accuracy
(Precision/Recall/F1 of predicted `supported`/`partial`/`missing` against
a *real*, rubric-labeled ground truth, as opposed to score-level
agreement against a holistic human grade) — that needs Dataset A
(RiceChem), which actually has rubric criteria; Dataset B does not.

## Why `grading/` has real numbers and the rest don't

Section 52 Rule 1 of the project spec: *"Do not fabricate research
results. If a metric has not been experimentally obtained, display 'Not
evaluated yet.'"* The inverse matters just as much: once a metric *has*
been experimentally obtained, it belongs here, run honestly, caveats and
all — not held back until every other metric catches up. `grading/` was
run because Dataset B (Pecuchova et al.) is openly available with no
access gate; `recognition/` and the criterion-level half of `grading/`
are blocked on datasets that are gated or unreachable from this build's
sandbox (see `docs/datasets.md`), not on any remaining engineering work.

The application itself (`backend/services/`, `backend/api/`) is real,
tested, working code independent of any of this — see `tests/` (34
passing) for that. This folder is specifically about *research claims
against external benchmarks*, which is what's still partially open.

