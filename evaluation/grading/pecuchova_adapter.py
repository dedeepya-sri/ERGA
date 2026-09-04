"""
Dataset-specific preprocessing for the Pecuchova et al. dataset (Dataset B,
see docs/datasets.md). Two things this file exists to solve, both specific
to *this* dataset's particular shape — not core ERGA logic, which is why
they live here in evaluation/ rather than in backend/services/:

1. The dataset provides no rubric criteria — just Question, Answer,
   Reference, and two human letter grades. ERGA needs criteria to grade
   anything. This module derives a lightweight pseudo-rubric by chunking
   the reference answer into roughly-equal word-count segments, each an
   equally-weighted criterion. This is a stand-in for a real
   faculty-authored rubric, not a claim that it IS one — see the
   methodology caveat printed at the top of every generated report.

2. Every text field in this CSV has had ALL punctuation stripped —
   verified empirically before writing this (zero periods, zero commas
   across all 1,885 rows: see the investigation in this project's commit
   history / conversation log). backend/services/segmentation.py's
   sentence splitter has nothing to split on and would treat each answer
   as a single giant segment, so this module chunks by word count
   instead, for both the reference (-> criteria) and the student answer
   (-> evidence segments).
"""
from __future__ import annotations

from dataclasses import dataclass

# Standard ECTS scale, worst -> best.
LETTER_ORDER = ["Fx", "E", "D", "C", "B", "A"]
_ORDINAL = {letter: i for i, letter in enumerate(LETTER_ORDER)}

# Standard ECTS percentage bands. Midpoints are used to place a letter
# grade on the same 0-100 numeric scale as the AI's score, for MAE/RMSE/
# Pearson; percent_to_letter is the inverse, used to bucket the AI's
# continuous score into a comparable category for Kappa.
_PERCENT_MIDPOINT = {"Fx": 25.0, "E": 55.0, "D": 65.0, "C": 75.0, "B": 85.0, "A": 95.0}
_PERCENT_BANDS = [(90.0, "A"), (80.0, "B"), (70.0, "C"), (60.0, "D"), (50.0, "E"), (0.0, "Fx")]


def letter_to_ordinal(letter: str) -> int:
    return _ORDINAL[letter]


def letter_to_percent_midpoint(letter: str) -> float:
    return _PERCENT_MIDPOINT[letter]


def percent_to_letter(pct: float) -> str:
    for threshold, letter in _PERCENT_BANDS:
        if pct >= threshold:
            return letter
    return "Fx"


def chunk_text(text: str, target_words: int, min_chunks: int = 1, max_chunks: int = 8) -> list[str]:
    """
    Splits `text` into `n` roughly-equal word-count chunks, where n is
    chosen so each chunk is close to `target_words` long (clamped to
    [min_chunks, max_chunks]). Stand-in for sentence segmentation on this
    dataset's punctuation-free text.
    """
    words = text.split()
    if not words:
        return []
    n = max(min_chunks, min(max_chunks, round(len(words) / target_words)))
    chunk_size = len(words) / n
    chunks = []
    for i in range(n):
        start = round(i * chunk_size)
        end = round((i + 1) * chunk_size) if i < n - 1 else len(words)
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


@dataclass
class DerivedCriterion:
    description: str
    marks: float


def derive_reference_rubric(
    reference_text: str, max_marks: float = 100.0, target_words: int = 15
) -> list[DerivedCriterion]:
    """Chunks are equally weighted; the last one absorbs any rounding
    remainder so marks always sum exactly to max_marks (Section 21)."""
    chunks = chunk_text(reference_text, target_words=target_words, min_chunks=2, max_chunks=6)
    if not chunks:
        return [DerivedCriterion(description=reference_text, marks=max_marks)]
    per = round(max_marks / len(chunks), 4)
    criteria = [DerivedCriterion(description=c, marks=per) for c in chunks[:-1]]
    remainder = round(max_marks - per * (len(chunks) - 1), 4)
    criteria.append(DerivedCriterion(description=chunks[-1], marks=remainder))
    return criteria
