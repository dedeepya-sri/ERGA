# Research framing

## Core research question

Can a multimodal, rubric-grounded framework provide consistent and
explainable criterion-level grading of descriptive examination answers
while retaining human control over uncertain decisions?

### Secondary questions

1. Can typed, PDF, scanned, and handwritten answers be converted into a
   common representation? — **Yes for typed/PDF/scanned** (Phases 1–3,
   implemented and tested); handwriting recognition is architected but not
   genuinely solved in this build (see `docs/methodology.md` limitations).
2. Can student answer content be reliably aligned with individual rubric
   criteria? — Implemented via TF-IDF retrieval (`services/embeddings.py`);
   reliability against human judgments is an open, unevaluated question
   (Phase 7).
3. Can semantic retrieval identify supporting evidence for each criterion?
4. Can NLI/semantic reasoning distinguish supported, partially supported,
   and missing criteria?
5. Can rubric-based deterministic scoring improve transparency compared
   with holistic AI scoring?
6. Can recognition uncertainty be separated from grading uncertainty?
   — Implemented and enforced by construction (`services/confidence.py`
   never combines the two numbers).
7. Can low-confidence cases be automatically routed to faculty?
8. How closely does the system agree with human graders? — **Not
   evaluated yet.** Requires Dataset B (Pecuchova et al.) with its two
   independent human grader scores; see `evaluation/grading/`.

## Experimental hypotheses (Section 46)

| # | Hypothesis | Status |
|---|---|---|
| H1 | Criterion-level rubric-grounded grading will produce better agreement with human criterion-level judgments than holistic semantic scoring. | Not evaluated yet |
| H2 | Evidence retrieval will improve explanation quality. | Not evaluated yet |
| H3 | Deterministic rubric weighting will improve score reproducibility. | **Supported by construction** — `tests/test_grading_pipeline.py::test_scoring_is_deterministic_fixed_fraction` verifies identical input+config always reproduces identical marks. Human-facing reproducibility studies are still open. |
| H4 | Confidence-based human review will reduce high-risk grading errors. | **Tested, weakly supported** — `evaluation/grading/run_pecuchova_evaluation.py` checks whether rows the shipped system's real confidence formula would flag for review actually have higher AI-vs-human error than unflagged rows, on the full held-out Pecuchova set (n=1,508). They do (61.2 vs. 57.9 mean error) — but the gap is modest, likely because the same miscalibrated default thresholds that hurt scoring accuracy on this dataset also blunt confidence's ability to discriminate risky from safe rows (see `docs/methodology.md`). One domain, one scoring mode — not a general proof. |
| H5 | The framework can process multiple answer modalities through a common grading pipeline. | **Supported by construction** for typed/PDF/scanned — `tests/test_api_flow.py` exercises all three through the identical `grade_submission()` code path. Handwritten input reaches the same code path but recognition quality is unvalidated. |

None of the "not evaluated yet" rows are stand-ins for results we chose
not to report — they are genuinely unrun experiments, per the project's
own Rule 1 ("If a metric has not been experimentally obtained, display
'Not evaluated yet'").

## Research gap

The literature already demonstrates automated scoring, rubric scoring,
GenAI grading, handwriting grading, and explainability — each on its own.
This project's contribution is the *integration*:

```
MULTIMODAL + RUBRIC-GROUNDED + EVIDENCE-LINKED + DETERMINISTIC SCORING
+ SEPARATE UNCERTAINTY + HUMAN REVIEW
```

## What is actually novel (Section 34/35)

Not claimed: that automated grading, handwriting grading, or explainable
AI grading are new — they aren't. The defensible novelty claim is:

> An integrated multimodal, rubric-grounded framework that converts typed,
> PDF, scanned, and handwritten descriptive answers into a common
> representation, aligns answer evidence with individual rubric criteria,
> performs criterion-level semantic assessment, calculates marks
> deterministically from rubric weights, separates recognition confidence
> from grading confidence, and selectively escalates uncertain decisions
> to faculty with traceable evidence.

Five components make up that claim, each with a corresponding
implementation:

1. **Evidence-grounded rubric grading** — `services/nli.py`, `services/scoring.py`
2. **Multimodal common grading pipeline** — `services/extraction.py`,
   `services/ocr.py` feed the same `grade_submission()` in
   `services/grading_pipeline.py` regardless of input format
3. **Separate uncertainty types** — `services/confidence.py`
4. **Confidence-triggered faculty review** — `services/confidence.py` +
   `api/reviews.py`
5. **Auditable scoring** — every `CriterionResult` row stores its status,
   evidence, marks, confidence, and (if overridden) a linked `Review` row
   with reviewer/timestamp/reason (`database/models.py`)

## Base paper

Kumar, V. S., & Boulanger, D. (2021). Automated Essay Scoring and the Deep
Learning Black Box: How Are Rubric Scores Determined? *International
Journal of Artificial Intelligence in Education*, 31(3), 538–584.
DOI: [10.1007/s40593-020-00211-5](https://doi.org/10.1007/s40593-020-00211-5)

Used as the conceptual journal base for rubric-level scoring,
interpretability, and deep-learning/NLP assessment generally.

## Supporting papers

**Sonkar, S., Ni, K., Tran Lu, L., Kincaid, K., Hutchinson, J. S., &
Baraniuk, R. G. (2024).** Automated Long Answer Grading with RiceChem
Dataset. In *Artificial Intelligence in Education* (AIED 2024), LNCS
14829. Springer. DOI:
[10.1007/978-3-031-64302-6_12](https://doi.org/10.1007/978-3-031-64302-6_12).
Source of the rubric-entailment formulation this project's NLI layer
follows, and of Dataset A.

**Pecuchova, J., Benko, Ľ., & Drlik, M. (2025).** Automated Grading of
Open-Ended Questions in Higher Education Using GenAI Models. *International
Journal of Artificial Intelligence in Education*, 35, 3813–3846. DOI:
[10.1007/s40593-025-00517-2](https://doi.org/10.1007/s40593-025-00517-2).
Studies 1,885 university responses, comparing GenAI and sentence-embedding
models against two human graders — the external validation target for
Phase 7. Source of Dataset B.

**Pinto, W. N., Jr., & Shin, J. (2025).** Evaluating the Consistency and
Reliability of Attribution Methods in Automated Short Answer Grading (ASAG)
Systems: Toward an Explainable Scoring System. *Journal of Educational
Measurement*, 62, 248–281. DOI:
[10.1111/jedm.12438](https://doi.org/10.1111/jedm.12438). Supports the
explainability/evidence-reliability research direction — relevant to any
future ablation of the evidence-retrieval component (Section 44's Model B
vs Model C).

**Liu, T., Chatain, J., Kobel-Keller, L., Kortemeyer, G., Willwacher, T., &
Sachan, M. (2026).** AI-assisted automated short answer grading of
handwritten university-level mathematics exam. *Teaching Mathematics and
its Applications*, 45(1), 84–105. DOI:
[10.1093/teamat/hrag010](https://doi.org/10.1093/teamat/hrag010) (arXiv
preprint: [2408.11728](https://arxiv.org/abs/2408.11728)). Supports the
handwriting + uncertainty + human-verification research direction; its
finding that GPT-4 gave "reliable... initial grading, subject to
subsequent human verification" is the same posture this project takes
toward handwritten input by construction (`ocr.handwriting_force_review`
in `config/model_config.yaml`).

## Positioning

This is a **human-in-the-loop academic assessment framework**, not an
autonomous replacement for teachers. The system's purpose is to assist,
explain, standardize, flag uncertainty, and let faculty decide — not to
replace faculty (Section 53).
