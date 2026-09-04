"""Unit tests for evaluation/grading/pecuchova_adapter.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evaluation" / "grading"))

from pecuchova_adapter import (  # noqa: E402
    chunk_text,
    derive_reference_rubric,
    letter_to_ordinal,
    letter_to_percent_midpoint,
    percent_to_letter,
)


def test_chunk_text_splits_roughly_evenly():
    text = " ".join(f"word{i}" for i in range(60))
    chunks = chunk_text(text, target_words=15, min_chunks=2, max_chunks=6)
    assert len(chunks) == 4  # 60 / 15
    # every word must survive, in order, none duplicated or dropped
    rejoined = " ".join(chunks).split()
    assert rejoined == text.split()


def test_chunk_text_respects_min_and_max_chunks():
    short_text = "just a few words here"
    chunks = chunk_text(short_text, target_words=15, min_chunks=2, max_chunks=6)
    assert len(chunks) >= 2  # min_chunks floor, even though target_words would suggest 1

    long_text = " ".join(f"w{i}" for i in range(500))
    chunks = chunk_text(long_text, target_words=15, min_chunks=2, max_chunks=6)
    assert len(chunks) <= 6  # max_chunks ceiling


def test_chunk_text_handles_empty_string():
    assert chunk_text("", target_words=15) == []


def test_derive_reference_rubric_marks_sum_exactly_to_max_marks():
    ref = " ".join(f"concept{i}" for i in range(80))
    criteria = derive_reference_rubric(ref, max_marks=100.0)
    total = sum(c.marks for c in criteria)
    assert abs(total - 100.0) < 0.01  # Section 21: SUM(criteria marks) == max_marks


def test_derive_reference_rubric_handles_very_short_reference():
    criteria = derive_reference_rubric("short answer", max_marks=100.0)
    assert len(criteria) >= 1
    assert abs(sum(c.marks for c in criteria) - 100.0) < 0.01


def test_derive_reference_rubric_criteria_text_covers_full_reference():
    ref = "functional requirements define what the system must do nonfunctional requirements define how well it must do it"
    criteria = derive_reference_rubric(ref, max_marks=100.0)
    rejoined = " ".join(c.description for c in criteria)
    assert rejoined.split() == ref.split()


def test_grade_conversion_ordinal_is_monotonic_with_letter_quality():
    ordinals = [letter_to_ordinal(letter) for letter in ["Fx", "E", "D", "C", "B", "A"]]
    assert ordinals == sorted(ordinals)  # strictly increasing worst -> best


def test_grade_conversion_percent_midpoints_are_monotonic():
    percents = [letter_to_percent_midpoint(letter) for letter in ["Fx", "E", "D", "C", "B", "A"]]
    assert percents == sorted(percents)


def test_percent_to_letter_round_trips_through_band_midpoints():
    for letter in ["Fx", "E", "D", "C", "B", "A"]:
        midpoint = letter_to_percent_midpoint(letter)
        assert percent_to_letter(midpoint) == letter


def test_percent_to_letter_boundary_values():
    assert percent_to_letter(95.0) == "A"
    assert percent_to_letter(90.0) == "A"
    assert percent_to_letter(89.9) == "B"
    assert percent_to_letter(50.0) == "E"
    assert percent_to_letter(49.9) == "Fx"
    assert percent_to_letter(0.0) == "Fx"
    assert percent_to_letter(100.0) == "A"


def test_confidence_test_helper_direction_and_math():
    """
    Sanity-checks run_pecuchova_evaluation.py's H4 helper in isolation
    (not the real pipeline) — a manufactured case where "flagged" rows
    are deliberately the ones with bigger errors should be detected as
    such, and the arithmetic should be exact.

    Confidence is lowest right AT a threshold boundary (0.32 or 0.62 by
    default) and high far from either boundary in either direction —
    checked directly against services.nli._margin_confidence before
    picking these values, rather than assumed.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evaluation" / "grading"))
    from run_pecuchova_evaluation import test_confidence_flags_high_risk_rows
    from config.settings import load_config

    config = load_config()
    held_out_cached = [
        {"grade1": "A", "grade2": "A", "criteria": [{"max_marks": 100.0, "composite_score": 0.32}]},  # AT a boundary -> confidence 0.5, flagged
        {"grade1": "A", "grade2": "A", "criteria": [{"max_marks": 100.0, "composite_score": 0.62}]},  # AT a boundary -> confidence 0.5, flagged
        {"grade1": "A", "grade2": "A", "criteria": [{"max_marks": 100.0, "composite_score": 0.05}]},  # far from any boundary -> confidence 0.92, not flagged
        {"grade1": "A", "grade2": "A", "criteria": [{"max_marks": 100.0, "composite_score": 0.95}]},  # far from any boundary -> confidence 0.93, not flagged
    ]
    default_scores = [0.0, 0.0, 94.0, 96.0]  # boundary rows scored far from A's 95 midpoint; far-from-boundary rows close

    result = test_confidence_flags_high_risk_rows(held_out_cached, default_scores, config)
    assert result["n_flagged"] == 2
    assert result["n_not_flagged"] == 2
    assert result["mean_error_flagged"] == 95.0  # mean(|0-95|, |0-95|) = mean(95, 95) = 95
    assert result["mean_error_not_flagged"] == 1.0  # mean(|94-95|, |96-95|) = mean(1, 1) = 1
    assert result["mean_error_flagged"] > result["mean_error_not_flagged"]
