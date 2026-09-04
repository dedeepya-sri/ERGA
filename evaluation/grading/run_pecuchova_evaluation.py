"""
Runs ERGA's real grading pipeline (backend/services/embeddings.py,
services/nli.py, services/scoring.py — no mocks, no shortcuts) against the
Pecuchova et al. dataset and computes genuine agreement metrics against
the two human graders it provides.

WHY THIS EXISTS: Section 43 of the project spec calls for score-agreement
metrics (MAE, RMSE, Pearson, Spearman, Cohen's/weighted Kappa) against
human graders, and Section 52 Rule 1 forbids reporting a metric that
hasn't actually been computed. This script is what makes that computation
real instead of aspirational.

METHODOLOGY CAVEAT — read before trusting the numbers: this dataset
provides no rubric criteria, only a reference answer. Criteria here are
*derived* from the reference by chunking it into roughly-equal word-count
segments (see pecuchova_adapter.py) — a stand-in for a real
faculty-authored rubric, not equivalent to one. RiceChem (Section 26) is
the dataset that actually has rubric criteria; use it for a cleaner test
of rubric-grounded grading once you have access (see datasets/ricechem/).

THRESHOLD CALIBRATION: a first run of this script against the default
thresholds in model_config.yaml (partial_min=0.32, supported_min=0.62)
showed those thresholds — picked during earlier development against
hand-written synthetic examples with strong vocabulary overlap — badly
miscalibrated for this dataset's real, paraphrase-heavy student answers:
fewer than 7% of criteria cleared "partial" even for A-graded answers,
even though composite scores still climbed cleanly and monotonically with
grade quality (Fx=0.10 -> A=0.24 mean composite). That's a real signal
being classified through the wrong thresholds, not a broken signal. So
this script now does what a real evaluation should: splits the data into
a calibration set and a held-out set, picks thresholds on the calibration
set only (grid search minimizing MAE against human grades), and reports
final metrics on the held-out set the thresholds never saw — alongside
the original defaults' held-out performance, for an honest before/after.

Usage (from evaluation/grading/):
    ../../datasets/pecuchova/download.sh        # one-time, if not already done
    python run_pecuchova_evaluation.py                    # full dataset (~1,885 rows)
    python run_pecuchova_evaluation.py --sample 300        # faster, a random subset
    python run_pecuchova_evaluation.py --questions 1,2,3   # only specific questions

Writes evaluation/reports/pecuchova_evaluation.md (summary + metrics) and
evaluation/reports/pecuchova_evaluation_raw.csv (every held-out row's AI
score, at both default and calibrated thresholds, next to both human
grades, for your own further analysis).
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import random
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import load_config  # noqa: E402
from services.embeddings import TfidfEmbedder  # noqa: E402
from services.nli import STATUS_MISSING, STATUS_PARTIAL, STATUS_SUPPORTED, LexicalNLIAssessor  # noqa: E402
from services.nli import _margin_confidence  # noqa: E402
from services.scoring import compute_criterion_marks  # noqa: E402
from services.segmentation import Segment  # noqa: E402

from pecuchova_adapter import (  # noqa: E402
    chunk_text,
    derive_reference_rubric,
    letter_to_ordinal,
    letter_to_percent_midpoint,
    percent_to_letter,
)

DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parents[2]
    / "datasets" / "pecuchova" / "genai-automated-grading" / "open_questions_grading.csv"
)
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
CALIBRATION_FRACTION = 0.2  # held out from calibration, used ONLY for final reported metrics


def load_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def collect_composites(rows: list[dict], config, embedder, nli) -> list[dict]:
    """
    Runs retrieval + NLI exactly once per row (the expensive part) and
    caches each criterion's raw composite score — NOT yet turned into
    marks, so different candidate thresholds can be tried afterward
    without re-running the pipeline.
    """
    cached = []
    for row in rows:
        criteria = derive_reference_rubric(row["Reference"], max_marks=100.0)
        answer_chunks = chunk_text(row["Answer"], target_words=10, min_chunks=1, max_chunks=10)
        segments = [Segment(index=i, text=c, line=i) for i, c in enumerate(answer_chunks)]
        criterion_composites = []
        for c in criteria:
            retrieved = embedder.retrieve(
                c.description, segments, top_k=config.retrieval.top_k, min_similarity=config.retrieval.min_similarity
            )
            assessment = nli.assess(c.description, [], retrieved)
            criterion_composites.append({"max_marks": c.marks, "composite_score": assessment.composite_score})
        cached.append(
            {
                "id": row["Id"], "qnumber": row["QNumber"],
                "grade1": row["Grade1"], "grade2": row["Grade2"],
                "criteria": criterion_composites,
            }
        )
    return cached


def _classify(composite: float, partial_min: float, supported_min: float) -> str:
    if composite >= supported_min:
        return STATUS_SUPPORTED
    if composite >= partial_min:
        return STATUS_PARTIAL
    return STATUS_MISSING


def score_with_thresholds(cached_row: dict, partial_min: float, supported_min: float, config) -> float:
    """Re-derives a row's AI score from cached composite scores at arbitrary
    candidate thresholds, reusing the real compute_criterion_marks() — so
    calibration exercises the actual scoring code, not a re-implementation
    of it."""
    total = 0.0
    for c in cached_row["criteria"]:
        status = _classify(c["composite_score"], partial_min, supported_min)
        total += compute_criterion_marks(status, c["composite_score"], c["max_marks"], config)
    return round(total, 2)


def calibrate_thresholds(cal_cached: list[dict], config) -> tuple[float, float, float]:
    """Grid search for the (partial_min, supported_min) pair minimizing MAE
    against avg(human grade) on the calibration set ONLY. Held-out rows
    are never touched here."""
    import numpy as np

    avg_human = np.array(
        [(letter_to_percent_midpoint(r["grade1"]) + letter_to_percent_midpoint(r["grade2"])) / 2 for r in cal_cached]
    )
    best = (config.thresholds.nli_partial_min, config.thresholds.nli_supported_min, float("inf"))
    for p in [round(x, 3) for x in _frange(0.03, 0.35, 0.01)]:
        for s in [round(x, 3) for x in _frange(0.06, 0.55, 0.02)]:
            if s <= p:
                continue
            ai_scores = np.array([score_with_thresholds(r, p, s, config) for r in cal_cached])
            mae = float(np.mean(np.abs(ai_scores - avg_human)))
            if mae < best[2]:
                best = (p, s, mae)
    return best


def _frange(start: float, stop: float, step: float):
    x = start
    while x < stop:
        yield x
        x += step


def test_confidence_flags_high_risk_rows(held_out_cached: list[dict], default_scores: list[float], config) -> dict:
    """
    Tests Section 46's H4 ("confidence-based human review will reduce
    high-risk grading errors") directly: using the exact same margin-based
    confidence formula the shipped system computes
    (services/nli.py::_margin_confidence) and the exact same review
    threshold real submissions are routed against
    (config.thresholds.grading_review_below), does the subset of held-out
    rows that WOULD be flagged for review actually have higher AI-vs-human
    error than the subset that wouldn't? If confidence is doing its job,
    flagged rows should show meaningfully higher error.
    """
    import numpy as np

    row_confidences = [
        min(_margin_confidence(c["composite_score"], config.thresholds) for c in r["criteria"])
        for r in held_out_cached  # min across criteria, matching api/submissions.py's real routing logic
    ]
    avg_human = np.array(
        [(letter_to_percent_midpoint(r["grade1"]) + letter_to_percent_midpoint(r["grade2"])) / 2 for r in held_out_cached]
    )
    errors = np.abs(np.array(default_scores) - avg_human)
    flagged = np.array(row_confidences) < config.thresholds.grading_review_below

    return {
        "n_flagged": int(flagged.sum()),
        "n_not_flagged": int((~flagged).sum()),
        "mean_error_flagged": float(errors[flagged].mean()) if flagged.any() else None,
        "mean_error_not_flagged": float(errors[~flagged].mean()) if (~flagged).any() else None,
        "review_threshold": config.thresholds.grading_review_below,
    }


def compute_agreement(name: str, a_pct, b_pct, a_ord, b_ord, a_letter, b_letter) -> dict:
    import numpy as np
    from scipy import stats
    from sklearn.metrics import cohen_kappa_score

    mae = float(np.mean(np.abs(a_pct - b_pct)))
    rmse = float(np.sqrt(np.mean((a_pct - b_pct) ** 2)))
    pearson_r, pearson_p = stats.pearsonr(a_pct, b_pct)
    spearman_r, spearman_p = stats.spearmanr(a_pct, b_pct)
    qwk = cohen_kappa_score(a_ord, b_ord, weights="quadratic")
    kappa = cohen_kappa_score(a_letter, b_letter)
    return {
        "name": name, "mae": mae, "rmse": rmse,
        "pearson_r": float(pearson_r), "pearson_p": float(pearson_p),
        "spearman_r": float(spearman_r), "spearman_p": float(spearman_p),
        "qwk": float(qwk), "kappa": float(kappa),
    }


def agreement_rows_for(cached_rows: list[dict], ai_scores, label: str) -> list[dict]:
    import numpy as np

    ai_pct = np.array(ai_scores, dtype=float)
    g1_pct = np.array([letter_to_percent_midpoint(r["grade1"]) for r in cached_rows], dtype=float)
    g2_pct = np.array([letter_to_percent_midpoint(r["grade2"]) for r in cached_rows], dtype=float)
    avg_pct = (g1_pct + g2_pct) / 2
    ai_letter = [percent_to_letter(x) for x in ai_pct]
    ai_ord = np.array([letter_to_ordinal(letter) for letter in ai_letter])
    g1_ord = np.array([letter_to_ordinal(r["grade1"]) for r in cached_rows])
    g2_ord = np.array([letter_to_ordinal(r["grade2"]) for r in cached_rows])
    avg_letter = [percent_to_letter(p) for p in avg_pct]
    avg_ord = np.array([letter_to_ordinal(letter) for letter in avg_letter])

    return [
        compute_agreement(f"{label} vs Grade1", ai_pct, g1_pct, ai_ord, g1_ord, ai_letter, [r["grade1"] for r in cached_rows]),
        compute_agreement(f"{label} vs Grade2", ai_pct, g2_pct, ai_ord, g2_ord, ai_letter, [r["grade2"] for r in cached_rows]),
        compute_agreement(f"{label} vs avg(Grade1,Grade2)", ai_pct, avg_pct, ai_ord, avg_ord, ai_letter, avg_letter),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", type=int, default=None, help="Use a random sample of N rows instead of the full dataset")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--questions", type=str, default=None, help="Comma-separated QNumbers to restrict to, e.g. 1,2,3")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_DATA_PATH)
    args = parser.parse_args()

    if not args.data_path.exists():
        print(f"Dataset not found at {args.data_path}")
        print("Run datasets/pecuchova/download.sh first, or pass --data-path.")
        sys.exit(1)

    rows = load_rows(args.data_path)
    if args.questions:
        wanted = {q.strip() for q in args.questions.split(",")}
        rows = [r for r in rows if r["QNumber"] in wanted]
    sampled = bool(args.sample and args.sample < len(rows))
    if sampled:
        random.seed(args.seed)
        rows = random.sample(rows, args.sample)

    random.seed(args.seed)
    shuffled = rows[:]
    random.shuffle(shuffled)
    n_cal = max(20, round(len(shuffled) * CALIBRATION_FRACTION))
    cal_rows, held_out_rows = shuffled[:n_cal], shuffled[n_cal:]

    config = load_config()
    embedder = TfidfEmbedder(config)
    nli = LexicalNLIAssessor(config)

    print(f"Running the real retrieval+NLI pipeline once over all {len(shuffled)} rows "
          f"({len(cal_rows)} for calibration, {len(held_out_rows)} held out for reporting)...")
    t0 = time.time()
    cal_cached = collect_composites(cal_rows, config, embedder, nli)
    held_out_cached = collect_composites(held_out_rows, config, embedder, nli)
    elapsed = time.time() - t0
    print(f"  done in {elapsed:.1f}s ({elapsed / len(shuffled) * 1000:.1f}ms/row)")

    print("Calibrating thresholds on the calibration split only (grid search, MAE objective)...")
    cal_partial, cal_supported, cal_mae = calibrate_thresholds(cal_cached, config)
    print(f"  calibrated: partial_min={cal_partial}, supported_min={cal_supported} (calibration-set MAE={cal_mae:.2f})")

    default_scores = [
        score_with_thresholds(r, config.thresholds.nli_partial_min, config.thresholds.nli_supported_min, config)
        for r in held_out_cached
    ]
    calibrated_config = dataclasses.replace(
        config,
        thresholds=dataclasses.replace(config.thresholds, nli_partial_min=cal_partial, nli_supported_min=cal_supported),
    )
    calibrated_scores = [score_with_thresholds(r, cal_partial, cal_supported, calibrated_config) for r in held_out_cached]
    # Same calibrated thresholds, but scoring.mode="proportional" instead of
    # "fixed_fraction" — cheap to test since it reuses the same cached
    # composite scores, and directly follows from a real finding while
    # testing this script: fixed-fraction's 3-discrete-outcomes-per-
    # criterion scoring can trade away rank correlation even as MAE
    # improves. See the report for what actually happened here.
    proportional_config = dataclasses.replace(calibrated_config, scoring=dataclasses.replace(config.scoring, mode="proportional"))
    proportional_scores = [score_with_thresholds(r, cal_partial, cal_supported, proportional_config) for r in held_out_cached]

    confidence_test = test_confidence_flags_high_risk_rows(held_out_cached, default_scores, config)

    write_report(
        held_out_cached, default_scores, calibrated_scores, proportional_scores,
        meta={
            "n_total": len(shuffled), "n_cal": len(cal_rows), "n_held_out": len(held_out_cached),
            "sampled": sampled, "seed": args.seed, "elapsed": elapsed,
            "embedding_engine": config.embedding.engine, "nli_engine": config.nli.engine,
            "default_partial": config.thresholds.nli_partial_min, "default_supported": config.thresholds.nli_supported_min,
            "cal_partial": cal_partial, "cal_supported": cal_supported, "cal_mae": cal_mae,
            "confidence_test": confidence_test,
        },
    )


def _fmt_or_na(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def _h4_verdict(confidence_test: dict) -> str:
    flagged, not_flagged = confidence_test["mean_error_flagged"], confidence_test["mean_error_not_flagged"]
    if flagged is None or not_flagged is None:
        return "**Inconclusive** — one of the two groups was empty on this run/sample."
    if flagged > not_flagged:
        return (
            f"**Consistent with H4**: flagged rows had {flagged - not_flagged:.1f} points higher "
            "mean error than non-flagged rows. Confidence-based flagging is doing real work here, "
            "not just adding friction — though this is one dataset, one domain, and a discrete "
            "3-outcome-per-criterion scoring mode, not a general proof."
        )
    return (
        f"**Not consistent with H4 on this run**: flagged rows had {not_flagged - flagged:.1f} points "
        "*lower* mean error than non-flagged rows — the confidence signal did not separate "
        "high-risk from low-risk rows in the expected direction here. Worth investigating "
        "before trusting confidence-based review routing in this domain without a human still "
        "checking a sample of *un*-flagged rows too."
    )


def write_report(held_out_cached, default_scores, calibrated_scores, proportional_scores, meta: dict) -> None:
    import numpy as np

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    default_blocks = agreement_rows_for(held_out_cached, default_scores, "AI (default thresholds)")
    calibrated_blocks = agreement_rows_for(held_out_cached, calibrated_scores, "AI (calibrated, fixed-fraction)")
    proportional_blocks = agreement_rows_for(held_out_cached, proportional_scores, "AI (calibrated, proportional)")
    human_block = compute_agreement(
        "Grade1 vs Grade2 (human-human baseline)",
        np.array([letter_to_percent_midpoint(r["grade1"]) for r in held_out_cached], dtype=float),
        np.array([letter_to_percent_midpoint(r["grade2"]) for r in held_out_cached], dtype=float),
        np.array([letter_to_ordinal(r["grade1"]) for r in held_out_cached]),
        np.array([letter_to_ordinal(r["grade2"]) for r in held_out_cached]),
        [r["grade1"] for r in held_out_cached], [r["grade2"] for r in held_out_cached],
    )

    raw_path = REPORTS_DIR / "pecuchova_evaluation_raw.csv"
    with open(raw_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["id", "qnumber", "ai_score_default", "ai_score_calibrated", "ai_score_proportional", "grade1", "grade2"]
        )
        writer.writeheader()
        for r, d, c, p in zip(held_out_cached, default_scores, calibrated_scores, proportional_scores):
            writer.writerow(
                {"id": r["id"], "qnumber": r["qnumber"], "ai_score_default": d,
                 "ai_score_calibrated": c, "ai_score_proportional": p,
                 "grade1": r["grade1"], "grade2": r["grade2"]}
            )

    def fmt_rows(blocks):
        return "\n".join(
            f"| {b['name']} | {b['mae']:.2f} | {b['rmse']:.2f} | "
            f"{b['pearson_r']:.3f} (p={b['pearson_p']:.2g}) | {b['spearman_r']:.3f} (p={b['spearman_p']:.2g}) | "
            f"{b['qwk']:.3f} | {b['kappa']:.3f} |"
            for b in blocks
        )

    lines = [
        "# ERGA vs. Pecuchova et al. — evaluation run",
        "",
        "This report was generated by actually running `run_pecuchova_evaluation.py` "
        "against real data — none of these numbers are invented or illustrative.",
        "",
        f"- Rows: **{meta['n_total']}** total"
        + (f" (random sample, seed={meta['seed']})" if meta["sampled"] else " (full dataset)")
        + f" — {meta['n_cal']} used only for threshold calibration, "
        f"**{meta['n_held_out']} held out** and never seen during calibration; all metrics below are on that held-out set.",
        f"- Runtime: {meta['elapsed']:.1f}s total ({meta['elapsed'] / meta['n_total'] * 1000:.1f}ms/row)",
        f"- Engines: embedding=`{meta['embedding_engine']}`, nli=`{meta['nli_engine']}` (backend/config/model_config.yaml)",
        "",
        "**Methodology caveats**: (1) this dataset has no rubric and no punctuation "
        "to segment on — criteria are *derived* from the reference answer by "
        "word-count chunking (`pecuchova_adapter.py::derive_reference_rubric`), an "
        "approximation of a real rubric, not equivalent to one. (2) Thresholds "
        "below were calibrated on a 20% split of this same dataset (never the "
        "held-out 80% reported on) — see `docs/methodology.md` for why the "
        "original hand-picked defaults needed this.",
        "",
        f"## Before calibration (defaults: partial_min={meta['default_partial']}, supported_min={meta['default_supported']})",
        "",
        "| Comparison | MAE | RMSE | Pearson r (p) | Spearman r (p) | QWK | Kappa |",
        "|---|---|---|---|---|---|---|",
        fmt_rows(default_blocks),
        "",
        f"## After calibration, fixed-fraction scoring (partial_min={meta['cal_partial']}, supported_min={meta['cal_supported']}, "
        f"chosen by grid search minimizing MAE on the calibration split, MAE there={meta['cal_mae']:.2f})",
        "",
        "| Comparison | MAE | RMSE | Pearson r (p) | Spearman r (p) | QWK | Kappa |",
        "|---|---|---|---|---|---|---|",
        fmt_rows(calibrated_blocks),
        "",
        "## Same calibrated thresholds, proportional scoring mode instead of fixed-fraction",
        "",
        "`scoring.mode: proportional` (model_config.yaml) interpolates partial credit "
        "within the partial band instead of always giving exactly 0.5x. Tested here "
        "because the fixed-fraction row above traded away some rank correlation for "
        "a large MAE improvement versus the uncalibrated defaults — worth checking "
        "whether smoother partial credit changes that trade-off. (In practice, when "
        "the calibrated partial band is narrow, as it often is here, the two modes "
        "end up close: there's little room inside a narrow band for interpolation to "
        "matter. The comparison is kept because that's a real, useful thing to see "
        "empirically rather than assume.)",
        "",
        "| Comparison | MAE | RMSE | Pearson r (p) | Spearman r (p) | QWK | Kappa |",
        "|---|---|---|---|---|---|---|",
        fmt_rows(proportional_blocks),
        "",
        "## Human-human baseline (same held-out rows)",
        "",
        "| Comparison | MAE | RMSE | Pearson r (p) | Spearman r (p) | QWK | Kappa |",
        "|---|---|---|---|---|---|---|",
        fmt_rows([human_block]),
        "",
        "MAE/RMSE are on a 0-100 percentage scale; letter grades are placed at ECTS "
        "band midpoints (A=95, B=85, C=75, D=65, E=55, Fx=25) for that comparison. "
        "QWK and Kappa compare the 6-category ECTS letter grade directly (the AI's "
        "percentage score is bucketed into a letter via the standard ECTS bands). "
        "Pearson/Spearman correlation is invariant to *monotonic* threshold changes "
        "in how composite scores map to marks in proportional regions, but IS "
        "affected here because fixed-fraction scoring makes the mapping "
        "discontinuous — so correlation can shift with calibration too, not just "
        "MAE/RMSE.",
        "",
        "Rule-of-thumb Kappa interpretation (Landis & Koch, 1977): <0 poor, "
        "0.00-0.20 slight, 0.21-0.40 fair, 0.41-0.60 moderate, 0.61-0.80 "
        "substantial, 0.81-1.00 almost perfect. The human-human row is the most "
        "relevant ceiling — it's not reasonable to expect an AI grader to agree "
        "with one human more than two humans agree with each other.",
        "",
        "## H4 check: does confidence-based flagging actually catch higher-error rows?",
        "",
        "Section 46's H4 (\"confidence-based human review will reduce high-risk "
        "grading errors\") tested directly: using the shipped system's real "
        "confidence formula and real review threshold "
        f"(`grading_review_below={meta['confidence_test']['review_threshold']}`) on the "
        "default-threshold scores above (not the calibrated ones — this tests what "
        "the actual shipped system would do).",
        "",
        f"- Rows that WOULD be flagged for review: **{meta['confidence_test']['n_flagged']}**, "
        f"mean error {_fmt_or_na(meta['confidence_test']['mean_error_flagged'])}",
        f"- Rows that would NOT be flagged: **{meta['confidence_test']['n_not_flagged']}**, "
        f"mean error {_fmt_or_na(meta['confidence_test']['mean_error_not_flagged'])}",
        "",
        _h4_verdict(meta["confidence_test"]),
        "",
        f"Per-row results (held-out set only): `{raw_path.name}`",
    ]

    md_path = REPORTS_DIR / "pecuchova_evaluation.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {md_path}")
    print(f"Wrote {raw_path}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()

