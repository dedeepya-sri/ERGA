# evaluation/grading/

## `run_pecuchova_evaluation.py` — real score-agreement evaluation

Grades the Pecuchova et al. dataset (Dataset B — see `docs/datasets.md`)
through ERGA's actual retrieval+NLI+scoring pipeline and computes real
agreement metrics (MAE, RMSE, Pearson, Spearman, QWK, Cohen's Kappa)
against its two independent human graders. Nothing here is mocked or
illustrative — see `docs/methodology.md`'s "Evaluation protocol" section
for the full write-up of what this found, including an important
caveat about why the calibrated thresholds it discovers should **not**
be copied into `model_config.yaml` as a universal default.

### Run it yourself

```bash
# one-time: fetch the dataset (openly available, no auth needed)
../../datasets/pecuchova/download.sh

# full dataset (~1,885 rows, ~10s)
python run_pecuchova_evaluation.py

# faster iteration on a subset
python run_pecuchova_evaluation.py --sample 300

# restrict to specific questions (QNumber 1-24)
python run_pecuchova_evaluation.py --questions 1,2,3
```

Writes `../reports/pecuchova_evaluation.md` (the full report: methodology,
before/after-calibration metrics, human-human baseline) and
`../reports/pecuchova_evaluation_raw.csv` (per-row AI scores next to both
human grades — IDs and numbers only, no student text, safe to share).

The versions of these two files already in `../reports/` were generated
by an actual run against the full dataset — check the file's own header
for the exact numbers rather than trusting anything summarized elsewhere,
since summaries can go stale as the code evolves and gets re-run.

### `pecuchova_adapter.py`

Dataset-specific preprocessing, kept separate from core ERGA code because
it solves problems specific to *this* dataset's shape, not general ones:

- **No rubric** — only a reference answer. `derive_reference_rubric()`
  builds a pseudo-rubric by chunking the reference into roughly-equal
  word-count segments. This is a stand-in for a real rubric, not
  equivalent to one — see `docs/datasets.md` for why RiceChem (Dataset A)
  is the dataset that actually has rubric criteria.
- **No punctuation anywhere** — verified empirically (zero periods, zero
  commas across all 1,885 rows) before writing this adapter.
  `backend/services/segmentation.py`'s sentence splitter has nothing to
  split on here, so `chunk_text()` uses word-count chunking instead, for
  both the reference (-> criteria) and the student answer (-> evidence
  segments).
- **Letter grades, not numbers** — `letter_to_ordinal`,
  `letter_to_percent_midpoint`, and `percent_to_letter` convert the
  dataset's standard 6-band ECTS letter scale (Fx/E/D/C/B/A) to and from
  numeric forms comparable with ERGA's percentage score.

`tests/test_pecuchova_adapter.py` covers all of the above.

### If you want to evaluate your own domain instead

`calibrate_thresholds()` in the main script is written to be reusable: it
takes cached (composite_score, human_grade) pairs and grid-searches for
the threshold pair minimizing MAE on a calibration split. If you have — or
can hand-label — a modest set of (criterion, answer, human_score) examples
in your own subject domain, you can reuse this same function rather than
trusting either ERGA's shipped defaults or this script's Pecuchova-derived
numbers blindly. **Cross-check any calibrated thresholds against a few
clear-cut cases before trusting them** (a criterion the answer obviously
satisfies; one it obviously contradicts) — that check is what caught the
Pecuchova-calibrated thresholds being unsafe to ship as a general default
in the first place.
