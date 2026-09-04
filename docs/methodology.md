# Methodology

## Scoring policy (Section 13)

For each criterion, the NLI assessor produces a **status**
(`supported` / `partially_supported` / `not_supported`) and a **composite
score** in [0, 1]. The scoring module (`services/scoring.py`) then applies
one of two modes, set in `model_config.yaml`:

- **`fixed_fraction`** (default): `marks = max_marks × fraction`, where
  `fraction` is a configured constant per status
  (supported=1.0, partial=0.5, missing=0.0 by default). This matches the
  spec's worked example exactly.
- **`proportional`**: for `partially_supported` only, the fraction is
  linearly interpolated across the partial-credit band
  (`[partial_min, supported_min)`) instead of always being exactly 0.5, so
  two partial answers of different strength don't necessarily get
  identical credit. Still fully deterministic.

The final mark is **always** `SUM(criterion marks)` — see
`services/scoring.py::total_marks()` — with no hidden curve or adjustment.

## Composite score (the lexical NLI engine)

```
key_terms      = content words of the criterion description + reference
                  concepts, minus rubric-instruction verbs ("explain",
                  "define", "name", "at least", ...) — see
                  RUBRIC_INSTRUCTION_WORDS in services/nli.py
coverage       = |key_terms found in evidence, not negated| / |key_terms|
similarity     = max TF-IDF cosine similarity across retrieved evidence
negated_terms  = key_terms found in evidence but only inside a negation
                  span (e.g. "does NOT use labelled data")
effective_sim  = similarity × (1 − |negated_terms| / |key_terms|)
composite      = similarity_weight × effective_sim + coverage_weight × coverage
```

Classification then applies two configured thresholds
(`thresholds.nli.supported_min`, `partial_min`) directly to `composite`.

## Grading confidence (the margin heuristic)

```
confidence = 0.5 + 0.5 × min(1, margin / band)
```

where `margin` is the composite score's distance from the nearest
threshold boundary and `band` is the width of the region that margin is
measured within. A score sitting exactly on a threshold gets ≈0.5; a score
deep inside a region approaches 1.0.

**This is a documented heuristic, not an empirically calibrated
probability.** It has not been validated against how often a "0.53
confidence" call is actually wrong — that validation is exactly what
Dataset B (Pecuchova et al., with its two human grader scores) would be
for. Until that experiment runs, treat the number as "how far from a
decision boundary," not "percent likely correct."

## Known limitations found while testing (not glossed over)

Building `tests/test_api_flow.py` surfaced two genuine, documented
limitations of the lexical baseline rather than hiding them behind a
cherry-picked demo:

1. **Topical overlap vs. specific relevance.** A criterion asking *why the
   water cycle matters for ecosystems*, graded against an answer that only
   *defines* the water cycle, scored as a low-confidence partial rather
   than a clean zero — because both texts share the words "water" and
   "cycle," even though the answer never addresses the actual question.
   Bag-of-words methods see shared subject vocabulary, not specific
   relevance to the sub-question. A transformer NLI engine (already
   implemented in `TransformerNLIAssessor`, just not runnable in this
   sandbox) would be expected to close this gap — that comparison is
   exactly what Section 44's ablation (Model B/C vs. the full system)
   should measure.
2. **Quantity requirements ("at least three...").** The lexical key-term
   matcher checks for the *presence* of concepts, not a *count* of how
   many were named. A student who correctly named three stages without
   writing the numeral "three" can register lower grading confidence than
   the correctness of their answer deserves. This is left as a documented
   gap rather than patched with a brittle number-word regex.

Both are called out explicitly in code comments
(`services/nli.py::_RUBRIC_INSTRUCTION_WORDS`) and in the integration test
that found them, rather than tuned away by cherry-picking easier examples.

## Bugs found and fixed during a follow-up QA pass

A later pass specifically investigating a report that PDF uploads seemed
"not to be considered" surfaced two real, concrete bugs — recorded here
rather than quietly fixed, per the same don't-smooth-over-what-testing-finds
spirit as the section above.

1. **OCR preprocessing was catastrophically slow.** `cv2.fastNlMeansDenoising`,
   the original default denoise step, cost 5–10+ *seconds per page* at a
   realistic 300 DPI scan size — long enough that an upload could plausibly
   read as "broken" even though it would eventually finish. Benchmarked
   against `medianBlur`, `GaussianBlur`, and `bilateralFilter` on both a
   clean synthetic scan and a deliberately noised one (Gaussian blur +
   pixel noise + an uneven lighting gradient): all three landed within
   ~0.005 of NLM's OCR confidence, at roughly 1/100th the runtime.
   `medianBlur` is now the default (`ocr.denoise_method` in
   `model_config.yaml`); `nlm` remains available for a specific case where
   it's worth the wait.
2. **Mixed-content PDFs silently dropped whole pages.** The original PDF
   extraction decided text-layer-vs-OCR once, for the *whole document*,
   using average characters-per-page. A PDF with page 1 typed and page 2
   an embedded photo/scan (a common shape — e.g. a typed answer with a
   diagram or handwritten continuation pasted in) could clear that
   average even though page 2 had zero extractable text, and page 2's
   content was never extracted at all — not flagged, not low-confidence,
   just absent. Extraction now decides per page
   (`services/extraction.py::extract_from_pdf`), so a page with no text
   layer gets OCR'd independently of how much text its neighbors have.
   `tests/test_api_flow.py::test_pdf_mixed_typed_and_scanned_pages_keeps_both`
   guards against a regression.

Both are now covered by tests specifically constructed to fail if either
bug came back, not just tests that happen to exercise the fixed code path.
Two smaller fixes from the same pass: password-protected/corrupted PDFs
previously could surface an *empty* error message (`"Extraction failed: "`)
— now translated into specific, actionable text
(`services/extraction.py::ExtractionError`) — and CORS was hardcoded to
port 5173 only, which would silently fail every request (not just PDF
ones) if Vite picked a different port; it now matches any localhost port.

## Evaluation protocol (Section 43)

**Score agreement — actually run.** `evaluation/grading/run_pecuchova_evaluation.py`
grades the real Pecuchova et al. dataset (Dataset B; 1,885 responses, 24
questions, two independent human graders on the standard 6-band ECTS
scale) through ERGA's real retrieval+NLI+scoring pipeline — no mocks. Full
results: `evaluation/reports/pecuchova_evaluation.md` and
`_raw.csv`. Headline numbers from the full-dataset run (1,508 held-out
rows, never seen during threshold calibration):

| | MAE (0-100) | Pearson r | Spearman r | QWK | Kappa |
|---|---|---|---|---|---|
| AI vs. human, default thresholds | 58.8 | 0.30 | 0.28 | 0.00 | 0.00 |
| AI vs. human, calibrated thresholds | 25.6 | 0.37 | 0.36 | 0.34 | 0.13 |
| Human vs. human (baseline/ceiling) | 2.1 | 0.95 | 0.95 | 0.95 | 0.83 |

**What this shows, stated plainly:**

1. The default thresholds (`partial_min=0.32`, `supported_min=0.62`) —
   picked during earlier development against hand-written synthetic
   examples with strong vocabulary overlap — were badly miscalibrated for
   this dataset's real, heavily-paraphrased short answers: fewer than 7%
   of criteria cleared "partial" even for A-graded students, even though
   composite scores still climbed monotonically with grade quality
   (Fx mean 0.10 -> A mean 0.24). The signal was real; the thresholds
   reading it were wrong for this domain.
2. Calibrating thresholds on a held-out 20% split (grid search minimizing
   MAE, evaluated only on the untouched 80%) roughly **halves MAE** and
   moves categorical agreement from none (Kappa ≈ 0, degenerate — the AI
   was classifying almost everything as the lowest band) to "slight"/
   "fair" (Kappa 0.13, QWK 0.34).
3. Even calibrated, there remains a large, honest gap to human-human
   agreement (Kappa 0.13 vs. 0.83). This is not a disappointing result to
   hide — it's exactly the kind of evidence that motivates both this
   project's human-in-the-loop design (nothing here claims to replace a
   grader) and the transformer-NLI upgrade path (`TransformerNLIAssessor`
   in `services/nli.py`), which a purely lexical approach can't fully
   close on heavily-paraphrased content.
4. `scoring.mode: proportional` was also tested against the same
   calibrated thresholds and came out very slightly *worse* than
   `fixed_fraction` on every metric in the full run — a real, useful
   negative result: a documented feature doesn't automatically help just
   because it sounds more sophisticated.

**Why the shipped defaults were NOT changed to the calibrated values —
this matters.** Before considering updating `model_config.yaml`, the
calibrated thresholds (`partial_min=0.03`, `supported_min=0.08`) were
cross-checked against the well-matched synthetic cases from
`tests/test_grading_pipeline.py`. They fail concretely: a criterion the
answer directly *contradicts* ("requires a catalyst" vs. "does not
require a catalyst") flips from correctly `not_supported` (composite
0.212, below even the original 0.32 bar) to wrongly `supported` (0.212
clears the calibrated 0.08 bar). The Pecuchova-calibrated thresholds
compensate for that dataset's specific, severe vocabulary mismatch by
loosening the bar so much that they stop rejecting genuinely wrong
answers elsewhere. **Threshold calibration is domain-specific and doesn't
transfer** — this is exactly why `run_pecuchova_evaluation.py` is written
as reusable calibration tooling (`calibrate_thresholds()`, cleanly
separated from the Pecuchova-specific data loading) rather than a
one-time fix. If you're grading a specific subject domain and want
better-calibrated thresholds for it, run this same methodology — split,
calibrate, cross-check against clear-cut cases before trusting it — on
your own domain's data, not on someone else's.

**Not yet run:**

- **Recognition** (OCR/HTR): Character Error Rate, Word Error Rate,
  against Dataset C (Handwritten ASAP-SAS) — blocked on downloading that
  dataset (see `docs/datasets.md`'s build-environment note).
- **Criterion-level grading** (Accuracy/Precision/Recall/F1 of predicted
  status vs. a *real* rubric-labeled status, as opposed to the
  reference-derived pseudo-rubric used above): needs Dataset A (RiceChem),
  which actually has rubric criteria — gated behind the authors' request
  form.
- **Evidence quality**: evidence precision/recall and unsupported-evidence
  rate — requires evidence-relevance annotations this project does not yet
  have; the metric definitions live in `evaluation/evidence/` as a stub
  pending that annotation effort. No evidence-quality number should be
  reported without first defining exactly how it was measured.

## Ablation studies (planned — Section 44, not yet run)

| Model | Configuration |
|---|---|
| A | Holistic semantic scoring only |
| B | Rubric + semantic retrieval |
| C | Rubric + retrieval + NLI |
| D | Rubric + retrieval + NLI + deterministic scoring |
| E | Full system + confidence + human review |

Every row is reachable purely through `model_config.yaml` toggles and
`services/scoring.py`'s mode flag — no separate codebase needed per
ablation arm.

## Baselines (planned — Section 45, not yet run)

TF-IDF + regression/classification; Sentence-BERT similarity alone;
Transformer/NLI alone; LLM-based holistic grading (where feasible, subject
to Section 50's "don't send student answers to external APIs by default").
