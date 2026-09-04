"""
Confidence-aware human review routing (Sections 16-18).

Two confidence scores are tracked completely separately and are NEVER
blended into one number (Section 16: "Never combine these blindly"):

  * recognition_confidence — how confident we are that OCR/extraction
    correctly captured the student's actual text. 1.0 for typed answers
    (nothing to recognize) and for any text a human has manually corrected;
    the OCR engine's own mean confidence otherwise.

  * grading_confidence — how confident the grading engine is that its
    SUPPORTED / PARTIALLY_SUPPORTED / NOT_SUPPORTED call for a given
    criterion is correct (services/nli.py's margin-based confidence).

Either one being low is independently sufficient to trigger faculty review
(Section 17) — a perfectly-recognized answer can still get an ambiguous
grading call, and a confidently-graded answer is worthless if OCR mangled
the text it was graded on.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config.settings import ThresholdsConfig


@dataclass
class ReviewDecision:
    review_required: bool
    reasons: list[str] = field(default_factory=list)


def criterion_review_reasons(
    criterion_label: str,
    grading_confidence: float,
    th: ThresholdsConfig,
) -> list[str]:
    if grading_confidence < th.grading_review_below:
        return [
            f"Low grading confidence on {criterion_label} "
            f"({grading_confidence:.2f} < {th.grading_review_below:.2f})"
        ]
    return []


def submission_review_decision(
    recognition_confidence: float,
    criterion_reason_lists: list[list[str]],
    th: ThresholdsConfig,
    force_review: bool = False,
    force_reason: str | None = None,
) -> ReviewDecision:
    reasons: list[str] = []

    if recognition_confidence < th.recognition_review_below:
        reasons.append(
            f"Low recognition confidence "
            f"({recognition_confidence:.2f} < {th.recognition_review_below:.2f})"
        )

    for r in criterion_reason_lists:
        reasons.extend(r)

    if force_review and force_reason:
        reasons.append(force_reason)

    return ReviewDecision(review_required=bool(reasons) or force_review, reasons=reasons)
